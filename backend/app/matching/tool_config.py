"""What menu import needs to run the tool-calling matching layer (E10, `app.matching.tool_layer`).

`tool_layer.py`, its prompt and its Gemini adapter are pinned by SHA-256 for the held-out
evaluation (ai/docs/i3_eval_freeze.md 4.10), so the plumbing the server adds around them lives here:

- `ToolLayerConfig`: the model adapter and the per-import request cap (MATCHING_LLM_MAX_CALLS).
  Menu import gets it instead of `LLMLayerConfig` when MATCHING_LLM_MODE=tools.
- `CappedToolLLM`: the adapter for one import. Every conversation turn is one model request and
  counts toward the cap. Past the cap a turn raises `ToolCallCapReached`, which `ToolEngine`
  treats like any failure: that photo, and every photo after it, keeps its rule results. A
  transient API error (HTTP 429/5xx, network, timeout) is tried once more after a short wait, as
  the M3a adapter does (2 attempts, the retry not counted toward the cap); any other error, or
  a second failure, fails the photo's conversation.
- Wall-clock bounds. `GeminiToolLLM` calls the SDK directly with only its request timeout (60 s),
  and a stalled connection may never trip it (in P14 one hung for 50+ minutes), which would leave
  the import in `processing`. So every turn runs in a daemon worker thread and is abandoned after
  TURN_TIMEOUT_S (75 s, the M3a `WALL_TIMEOUT_S`), and one photo's conversation gets at most
  PHOTO_TIMEOUT_S in all (`start_photo`). Either raises `ToolCallTimeout`, which is not retried:
  `ToolEngine` treats it like any failure, so that photo keeps its rule results and the import
  goes on with the next photo. The abandoned thread may still finish later; it only fills a
  holder nobody reads any more (it never sees the database session), and the hung client is not
  used again: with `ToolLayerConfig.make_llm` every import starts with a new adapter and gets
  another after an abandoned turn, as `gemini.call_with_retries` (M3a) replaces a hung client.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from time import sleep
from typing import Any

import httpx

from app.matching.llm_layer import LLMLayerConfig
from app.matching.tool_layer import ToolLLM

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 2  # as app.adapters.gemini_matching_llm (M3a)
RETRY_WAIT_S = 5.0  # the first backoff of app.extraction.gemini
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
TURN_TIMEOUT_S = 75.0  # as app.adapters.gemini_matching_llm.WALL_TIMEOUT_S (M3a): the SDK's 60 s plus a margin
# A conversation is at most tool_layer.MAX_TURNS (6) turns, about 3 in the dev evaluation at a few
# seconds each; past this, the photo keeps its rule results instead of holding the import.
PHOTO_TIMEOUT_S = 180.0

# Replaced in tests.
monotonic = time.monotonic


@dataclass(frozen=True)
class ToolLayerConfig:
    """MATCHING_LLM_MODE=tools: what menu import needs to run the tool layer.

    `make_llm`, when set, builds a new adapter (a new client): one per import and another after a
    turn is abandoned, so a client holding a hung connection is not used again. Without it (tests)
    `llm` is used throughout.
    """

    llm: ToolLLM
    max_calls: int
    make_llm: Callable[[], ToolLLM] | None = None


# The LLM matching layer menu import runs, or None when it is off.
MatchingLayerConfig = LLMLayerConfig | ToolLayerConfig


class ToolCallCapReached(Exception):
    """The import used up MATCHING_LLM_MAX_CALLS model requests."""


class ToolCallTimeout(Exception):
    """A turn got no answer within its wall-clock limit, or the photo's conversation ran out of time.
    Not a `TimeoutError`, so it is not retried: the photo keeps its rule results."""


class CappedToolLLM:
    """`ToolLLM` for one menu import: the request cap, one retry of a transient error, and the
    wall-clock limits per turn and per photo (call `start_photo` before each photo's conversation).

    `stats` counts requests (ok, error, retry, timeout) and turns refused by the cap (cap_reached)
    or because the photo's time ran out (photo_timeout).
    """

    def __init__(
        self,
        llm: ToolLLM,
        max_calls: int,
        *,
        make_llm: Callable[[], ToolLLM] | None = None,
        turn_timeout_s: float | None = None,
        photo_timeout_s: float | None = None,
    ) -> None:
        self.make_llm = make_llm
        self.llm = make_llm() if make_llm is not None else llm
        self.max_calls = max_calls
        self.turn_timeout_s = TURN_TIMEOUT_S if turn_timeout_s is None else turn_timeout_s
        self.photo_timeout_s = PHOTO_TIMEOUT_S if photo_timeout_s is None else photo_timeout_s
        self.calls = 0
        self.stats: Counter[str] = Counter()
        self._photo_deadline: float | None = None

    def start_photo(self) -> None:
        """The next turns belong to a new photo's conversation, which gets PHOTO_TIMEOUT_S in all."""
        self._photo_deadline = monotonic() + self.photo_timeout_s

    def step(self, system: str, history: list[dict], tools: list[dict]) -> dict:
        if self.calls >= self.max_calls:
            self.stats["cap_reached"] += 1
            raise ToolCallCapReached(f"{self.max_calls} model requests per import")
        self._check_photo_time()
        self.calls += 1
        attempts = 0
        while True:
            attempts += 1
            try:
                output = self._step_with_deadline(system, history, tools)
            except ToolCallTimeout:
                self.stats["timeout"] += 1
                raise
            except Exception as error:
                if attempts < MAX_ATTEMPTS and is_transient(error):
                    self.stats["retry"] += 1
                    sleep(RETRY_WAIT_S)
                    self._check_photo_time()
                    continue
                # The type only: messages can carry request details.
                logger.warning("matching LLM tools call failed: %s", type(error).__name__)
                self.stats["error"] += 1
                raise
            self.stats["ok"] += 1
            return output

    def _check_photo_time(self) -> None:
        if self._photo_deadline is not None and monotonic() >= self._photo_deadline:
            self.stats["photo_timeout"] += 1
            logger.warning("matching LLM tools conversation stopped: over %.0f s for one photo", self.photo_timeout_s)
            raise ToolCallTimeout(f"over {self.photo_timeout_s} s for one photo")

    def _step_with_deadline(self, system: str, history: list[dict], tools: list[dict]) -> dict:
        """One `llm.step` in a daemon thread, abandoned after the turn limit or what is left of the photo's time.

        The thread gets its own copy of the history and writes only to `box`, which nobody reads once
        the turn is abandoned, so a late answer changes nothing (and the thread never sees the
        database session). The adapter it used is replaced, as its client may hold the hung connection.
        """
        limit = self.turn_timeout_s
        if self._photo_deadline is not None:
            limit = max(0.0, min(limit, self._photo_deadline - monotonic()))
        llm = self.llm
        box: dict[str, Any] = {}

        def run() -> None:
            try:
                box["result"] = llm.step(system, list(history), tools)
            except BaseException as error:  # handed to the caller
                box["error"] = error

        worker = threading.Thread(target=run, name="matching-llm-tools-turn", daemon=True)
        worker.start()
        worker.join(limit)
        if worker.is_alive():
            logger.warning("matching LLM tools call abandoned: no response within %.0f s", limit)
            if self.make_llm is not None:
                self.llm = self.make_llm()
            raise ToolCallTimeout(f"no response within {limit:.0f} s")
        if "error" in box:
            raise box["error"]
        return box["result"]


def is_transient(error: Exception) -> bool:
    if isinstance(error, (TimeoutError, ConnectionError, httpx.TimeoutException, httpx.NetworkError)):
        return True
    for attr in ("code", "status_code"):
        value = getattr(error, attr, None)
        if isinstance(value, int):
            return value in RETRY_STATUS
    return False
