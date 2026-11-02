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
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from time import sleep

import httpx

from app.matching.llm_layer import LLMLayerConfig
from app.matching.tool_layer import ToolLLM

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 2  # as app.adapters.gemini_matching_llm (M3a)
RETRY_WAIT_S = 5.0  # the first backoff of app.extraction.gemini
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


@dataclass(frozen=True)
class ToolLayerConfig:
    """MATCHING_LLM_MODE=tools: what menu import needs to run the tool layer."""

    llm: ToolLLM
    max_calls: int


# The LLM matching layer menu import runs, or None when it is off.
MatchingLayerConfig = LLMLayerConfig | ToolLayerConfig


class ToolCallCapReached(Exception):
    """The import used up MATCHING_LLM_MAX_CALLS model requests."""


class CappedToolLLM:
    """`ToolLLM` for one menu import: the request cap and one retry of a transient error.

    `stats` counts requests (ok, error, retry) and turns refused by the cap (cap_reached).
    """

    def __init__(self, llm: ToolLLM, max_calls: int) -> None:
        self.llm = llm
        self.max_calls = max_calls
        self.calls = 0
        self.stats: Counter[str] = Counter()

    def step(self, system: str, history: list[dict], tools: list[dict]) -> dict:
        if self.calls >= self.max_calls:
            self.stats["cap_reached"] += 1
            raise ToolCallCapReached(f"{self.max_calls} model requests per import")
        self.calls += 1
        attempts = 0
        while True:
            attempts += 1
            try:
                output = self.llm.step(system, history, tools)
            except Exception as error:
                if attempts < MAX_ATTEMPTS and is_transient(error):
                    self.stats["retry"] += 1
                    sleep(RETRY_WAIT_S)
                    continue
                # The type only: messages can carry request details.
                logger.warning("matching LLM tools call failed: %s", type(error).__name__)
                self.stats["error"] += 1
                raise
            self.stats["ok"] += 1
            return output


def is_transient(error: Exception) -> bool:
    if isinstance(error, (TimeoutError, ConnectionError, httpx.TimeoutException, httpx.NetworkError)):
        return True
    for attr in ("code", "status_code"):
        value = getattr(error, attr, None)
        if isinstance(value, int):
            return value in RETRY_STATUS
    return False
