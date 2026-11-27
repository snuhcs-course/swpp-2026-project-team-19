"""Hybrid extraction over a ladder of routes (I5-P19): OpenRouter first, the Gemini API when it fails.

One photo is read by the first route that answers:

| stage | route                                                          | taken when                              |
|-------|----------------------------------------------------------------|-----------------------------------------|
| 0     | OpenRouter, the primary model (OpenRouter picks the provider)   | always tried first                      |
| 1     | OpenRouter, a fallback model (`models` in the same request)     | every provider of the primary failed    |
| 2     | Gemini API, the direct model (EXTRACTION_DIRECT_MODEL)          | the OpenRouter call failed, is paused,  |
|       |                                                                | or today's paid photos are used up      |
| 3     | Gemini API, the lite model (EXTRACTION_MODEL)                   | the stage 2 call failed (e.g. 429), or  |
|       |                                                                | stage 2 is off                          |
| 4     | none: AllRoutesFailedError, the photo is marked failed          | every call failed                       |

Stage 2 is optional: with EXTRACTION_DIRECT_MODEL empty or unset (`RouteSettings.direct` None) it
is not tried, the photo goes from stage 0 straight to stage 3, and `route.skipped` records
`{"stage": 2, "reason": "direct_disabled"}`. With a model set, stage 2 works as before.

Stages 0 and 1 are one request: OpenRouter moves on to the fallback models itself, and the answer's
`model` tells which stage it was. "The OpenRouter call failed" is any ModelCallError after its
retries, HTTP 402 (out of credits) included: stage 2 then keeps the service running without
spending more.

The circuit breaker keeps a dead OpenRouter from costing every photo its retries: after
`breaker_failures` failed OpenRouter calls in a row, stages 0 and 1 are skipped for
`breaker_cooldown_s` seconds; then one call is tried again, and its failure pauses them again. The
state lives in the process (the API runs as one process).

The daily paid limit (`budget`, app.services.paid_photo_budget) is the server's own spending
brake: the team's one OpenRouter key has no limit of its own. Once `daily_paid_limit` photos have
been sent to OpenRouter in a KST day, the rest of the day's photos start at stage 2. Nothing is
refused; the skipped stage is recorded with the reason `daily_paid_limit`.

An answer that arrived but is not valid output (cut at `max_tokens` twice, not the schema) fails
the photo as it does for the other extractors; it is not sent to the next route, because the
route worked. An answer cut at `max_tokens` is asked for once more first.

OCR runs once and every route gets the same lines, prompt and photo. The result is that of
hybrid_v2.extract_menu_hybrid_v2, and `meta["route"]` says which stage and model read the photo
and which stages were skipped and why. The same is logged: `extraction route stage=N ...`, at
WARNING for every stage but 0, so photos read by the lite model are found with
`extraction route stage=3`.
"""

import hashlib
import logging
import os
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from functools import cache
from pathlib import Path
from typing import Any, Protocol

from google import genai
from pydantic import ValidationError

from app.extraction import gemini, openrouter
from app.extraction.clova import ClovaSettings
from app.extraction.config import ExtractionSettings, _positive, load_settings
from app.extraction.edge_guard import DEFAULT_STRIP_PERMILLE, load_strip_permille
from app.extraction.errors import ExtractionConfigError, InvalidModelOutputError, ModelCallError
from app.extraction.hybrid import run_ocr, user_text
from app.extraction.hybrid_v2 import HybridExtractionV2, convert_output
from app.extraction.openrouter import OpenRouterSettings, load_openrouter_settings

logger = logging.getLogger(__name__)

# prompt setting -> (version recorded on the run, file)
PROMPTS = {"v2": ("hybrid-v2", "hybrid_prompt_v2.md"), "v2.1": ("hybrid-v2.1", "hybrid_prompt_v2_1.md")}
DEFAULT_PROMPT = "v2.1"
PATHS = {0: "openrouter", 1: "openrouter-fallback", 2: "gemini-direct", 3: "gemini-direct-lite"}


class AllRoutesFailedError(ModelCallError):
    """Stage 4: no route answered. `route` is what each stage did, for the failed run's record."""

    def __init__(self, message: str, *, attempts: int, route: dict[str, Any]) -> None:
        super().__init__(message, attempts=attempts)
        self.route = route


@dataclass(frozen=True)
class RouteSettings:
    openrouter: OpenRouterSettings
    direct: ExtractionSettings | None  # stage 2; None turns it off (EXTRACTION_DIRECT_MODEL empty)
    lite: ExtractionSettings  # stage 3
    prompt: str = DEFAULT_PROMPT
    breaker_failures: int = 3
    breaker_cooldown_s: float = 600
    daily_paid_limit: int = 300
    # Left and right strips (0-1000) where a whisky line with no option is a facing page's line
    # (app.extraction.edge_guard); 0 turns the guard off. Applied by the adapter, not by this module.
    edge_strip_permille: int = DEFAULT_STRIP_PERMILLE


class PaidBudget(Protocol):
    """Today's places for photos read through OpenRouter (app.services.paid_photo_budget.DailyPaidBudget)."""

    limit: int

    def try_reserve(self) -> date | None: ...

    def refund(self, day: date) -> None: ...


def load_route_settings() -> RouteSettings:
    """Read every setting of the ladder; raise ExtractionConfigError naming what is missing or invalid."""
    lite = load_settings()  # GEMINI_API_KEY, EXTRACTION_MODEL, EXTRACTION_THINKING_LEVEL
    direct_model = (os.getenv("EXTRACTION_DIRECT_MODEL") or "").strip()  # empty: stage 2 off
    # A free-tier 429 does not clear in a minute, so stage 2 gives up early and stage 3 takes over.
    direct_attempts = _positive("EXTRACTION_DIRECT_MAX_ATTEMPTS", 2, int)
    prompt = os.getenv("OPENROUTER_EXTRACTION_PROMPT") or DEFAULT_PROMPT
    if prompt not in PROMPTS:
        raise ExtractionConfigError(f"OPENROUTER_EXTRACTION_PROMPT must be one of {', '.join(PROMPTS)}, got {prompt!r}")
    return RouteSettings(
        openrouter=load_openrouter_settings(),
        direct=replace(lite, model=direct_model, max_attempts=direct_attempts) if direct_model else None,
        lite=lite,
        prompt=prompt,
        breaker_failures=_positive("OPENROUTER_BREAKER_FAILURES", RouteSettings.breaker_failures, int),
        breaker_cooldown_s=_positive("OPENROUTER_BREAKER_COOLDOWN_S", RouteSettings.breaker_cooldown_s, float),
        daily_paid_limit=_positive("OPENROUTER_DAILY_PHOTO_LIMIT", RouteSettings.daily_paid_limit, int),
        edge_strip_permille=load_strip_permille(),
    )


@cache
def load_prompt(prompt: str) -> str:
    # LF regardless of how git checked the file out, so the bytes match the evaluation runs.
    return Path(__file__).with_name(PROMPTS[prompt][1]).read_text(encoding="utf-8").replace("\r\n", "\n")


class CircuitBreaker:
    """Pauses a route after `threshold` failures in a row, for `cooldown_s` seconds. Thread-safe."""

    def __init__(self, threshold: int = 3, cooldown_s: float = 600, clock: Callable[[], float] = time.monotonic) -> None:
        self.threshold, self.cooldown_s, self._clock = threshold, cooldown_s, clock
        self._lock = threading.Lock()
        self._failures = 0
        self._open_until: float | None = None

    def allows(self) -> bool:
        """Closed: yes. Paused: no. Cooldown over: yes for one caller, the probe; the pause is
        renewed at once, so callers that arrive before the probe ends stay on the other routes. The
        probe's success closes the breaker; its failure pauses it again."""
        with self._lock:
            if self._open_until is None:
                return True
            now = self._clock()
            if now < self._open_until:
                return False
            self._open_until = now + self.cooldown_s
            return True

    def record_success(self) -> None:
        with self._lock:
            self._failures, self._open_until = 0, None

    def record_failure(self) -> bool:
        """Count one failure; True when the route is now paused."""
        with self._lock:
            self._failures += 1
            if self._failures < self.threshold:
                return False
            # Also after the cooldown: the one call that was let through failed, so pause again.
            self._open_until = self._clock() + self.cooldown_s
            return True


def extract_menu_routed(
    image: bytes,
    mime_type: str,
    clova: ClovaSettings,
    route: RouteSettings,
    breaker: CircuitBreaker,
    *,
    budget: PaidBudget | None = None,
    http_client: Any = None,
    gemini_client: Any = None,
    ocr_client: Any = None,
) -> dict[str, Any]:
    """OCR + the first route that answers, for one photo. Returns {"items", "meta"} like
    extract_menu_hybrid_v2; `meta["route"]` is {"stage", "path", "model", "provider", "skipped"}.

    `budget` is the server-wide daily limit on photos sent to OpenRouter; without it there is none.

    Raises ClovaOCRError when OCR fails, InvalidModelOutputError when a route answered with
    something that is not valid output, and AllRoutesFailedError when no route answered.
    """
    ocr = run_ocr(image, mime_type, clova, ocr_client)
    prompt = load_prompt(route.prompt)
    meta: dict[str, Any] = {
        "mode": "hybrid",
        "promptVersion": PROMPTS[route.prompt][0],
        "promptSha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "imageSha256": hashlib.sha256(ocr["prepared"]).hexdigest(),
        "ocr": {**ocr["ocr"], "provider": "clova-general-v2", "tableDetection": False, "lines": ocr["table"]},
        "rawOutput": None,
        "itemSources": None,
        "otherItems": None,
        "otherItemsDropped": None,
    }
    skipped: list[dict[str, Any]] = []
    reserved: date | None = None  # the KST day of the place taken in the daily paid budget

    if not breaker.allows():
        skipped.append({"stage": 0, "reason": "circuit_open"})
    elif budget is not None and not (reserved := budget.try_reserve()):
        skipped.append({"stage": 0, "reason": "daily_paid_limit", "limit": budget.limit})
        logger.warning("extraction route stage=0 skipped: daily_paid_limit (today's %d photos through OpenRouter "
                       "are used up, or could not be counted); starting at stage 2", budget.limit)
    else:
        try:
            call = _call_openrouter(route.openrouter, prompt, ocr, http_client)
        except ModelCallError as error:
            billed = getattr(error, "billed_usd", None)  # a cut answer arrived and was billed first
            # a request given up before its answer (wall-clock cap, read timeout) may be billed: keep the place
            abandoned = getattr(error, "abandoned_attempts", 0)
            if budget is not None and billed is None and not abandoned:
                budget.refund(reserved)  # OpenRouter did not answer: the photo was not read through it
            paused = breaker.record_failure()
            skipped.append(_skip(0, error) | ({"billedUsd": billed} if billed is not None else {})
                           | ({"abandonedAttempts": abandoned} if abandoned else {}))
            logger.warning("extraction route stage=0 failed (%s: %.200s)%s", type(error).__name__, error,
                           f"; OpenRouter is paused for {route.breaker_cooldown_s:.0f}s" if paused else "")
        else:
            breaker.record_success()
            return _finish(meta, call, skipped, ocr["table"])

    for stage, settings in ((2, route.direct), (3, route.lite)):
        if settings is None:  # stage 2 is off: no call
            skipped.append({"stage": stage, "reason": "direct_disabled"})
            continue
        try:
            call = _call_gemini(stage, settings, prompt, ocr, gemini_client)
        except ModelCallError as error:
            skipped.append(_skip(stage, error))
            logger.warning("extraction route stage=%d failed (%s: %.200s)", stage, type(error).__name__, error)
            continue
        return _finish(meta, call, skipped, ocr["table"])

    logger.error("extraction route stage=4: every route failed (%s)", "; ".join(_reason(s) for s in skipped))
    raise AllRoutesFailedError(
        "every extraction route failed: " + "; ".join(_reason(s) for s in skipped),
        attempts=sum(s.get("attempts", 0) for s in skipped),
        route={"stage": 4, "path": None, "model": None, "provider": None, "skipped": skipped},
    )


def _skip(stage: int, error: ModelCallError) -> dict[str, Any]:
    return {"stage": stage, "reason": type(error).__name__, "message": str(error)[:300], "attempts": error.attempts}


def _reason(skip: dict[str, Any]) -> str:
    return f"stage {skip['stage']} {skip['reason']}" + (f" ({skip['message']})" if "message" in skip else "")


def _call_openrouter(settings: OpenRouterSettings, prompt: str, ocr: dict[str, Any], client: Any) -> dict[str, Any]:
    """Stages 0 and 1. An answer cut at max_tokens is asked for once more; both calls are billed.

    When the second call fails, the ModelCallError carries `billed_usd` (what the cut answer cost):
    the photo did cost money, so its place in the daily paid budget is kept."""
    body = openrouter.build_body(settings, prompt, user_text(ocr["table"]), ocr["prepared"], ocr["preparedMime"],
                                 HybridExtractionV2.model_json_schema())
    started_at = datetime.now(UTC).isoformat()
    attempts, cost, truncated = 0, 0.0, 0
    while True:
        try:
            result = openrouter.call_with_retries(settings, body, client)
        except ModelCallError as error:
            if truncated:
                error.billed_usd = round(cost, 6)
            raise
        got = openrouter.answer(result.data)
        attempts += result.attempts
        cost += got["costUsd"] or 0
        if got["finishReason"] != "length" or truncated:
            break
        truncated += 1
        logger.warning("extraction route: the answer of %s was cut at max_tokens=%d; asking once more",
                       got["model"], settings.max_tokens)
    model = got["model"] or settings.model
    fallback = any(same_model(model, m) for m in settings.fallback_models)
    return {
        "stage": 1 if fallback else 0,
        "model": model,
        "provider": got["provider"],
        "text": got["text"],
        "status": "completed" if got["finishReason"] == "stop" else str(got["finishReason"]),
        "meta": {
            "requestedModel": settings.model,
            "fallbackModels": list(settings.fallback_models),
            "reasoningEffort": settings.reasoning_effort,
            "maxTokens": settings.max_tokens,
            "api": "openrouter chat completions",
            "generationId": got["generationId"],
            "startedAt": started_at,
            "latencyMs": result.latency_ms,
            "attempts": attempts,
            "truncatedAttempts": truncated,
            "inputTokens": got["inputTokens"],
            "outputTokens": got["outputTokens"],
            "thoughtTokens": got["thoughtTokens"],
            "totalTokens": got["totalTokens"],
            # What OpenRouter charged, a cut first answer included. None when it reported no cost.
            "costUsd": round(cost, 6) if got["costUsd"] is not None else None,
        },
    }


def same_model(answered: str, configured: str) -> bool:
    """The model OpenRouter says answered is `configured`: the same id, or that id with what OpenRouter
    adds to it, a dated snapshot (`-20261101`) or a variant (`:nitro`). A longer id that only starts
    with `configured` (`vendor/model-pro` for `vendor/model`) is another model."""
    return re.fullmatch(re.escape(configured) + r"(?:-\d{8}|:[\w.-]+)?", answered) is not None


def _call_gemini(stage: int, settings: ExtractionSettings, prompt: str, ocr: dict[str, Any], client: Any) -> dict[str, Any]:
    """Stages 2 and 3: the request of hybrid_v2.extract_menu_hybrid_v2, with this ladder's prompt."""
    request = gemini.build_request(settings, prompt, ocr["prepared"], ocr["preparedMime"],
                                   HybridExtractionV2.model_json_schema())
    request["input"][0]["text"] = user_text(ocr["table"])
    started_at = datetime.now(UTC).isoformat()
    result = gemini.call_with_retries(settings, request, client)
    interaction = result.interaction
    usage = getattr(interaction, "usage", None)
    return {
        "stage": stage,
        "model": settings.model,
        "provider": "Google AI Studio (direct)",
        "text": getattr(interaction, "output_text", None) or "",
        "status": str(getattr(interaction, "status", None)),
        "meta": {
            "thinkingLevel": settings.thinking_level,
            "sdk": f"google-genai {genai.__version__}",
            "api": "interactions",
            "startedAt": started_at,
            "latencyMs": result.latency_ms,
            "attempts": result.attempts,
            "inputTokens": getattr(usage, "total_input_tokens", None),
            "outputTokens": getattr(usage, "total_output_tokens", None),
            "thoughtTokens": getattr(usage, "total_thought_tokens", None),
            "totalTokens": getattr(usage, "total_tokens", None),
            "costUsd": None,  # the Gemini API reports no cost
        },
    }


def _finish(meta: dict[str, Any], call: dict[str, Any], skipped: list[dict[str, Any]],
            table: list[dict[str, Any]]) -> dict[str, Any]:
    stage = call["stage"]
    meta.update(call["meta"], model=call["model"], status=call["status"],
                route={"stage": stage, "path": PATHS[stage], "model": call["model"], "provider": call["provider"],
                       "skipped": skipped})
    logger.log(
        logging.INFO if stage == 0 else logging.WARNING,
        "extraction route stage=%d path=%s model=%s provider=%s input_tokens=%s output_tokens=%s "
        "thought_tokens=%s cost_usd=%s latency_ms=%s attempts=%s skipped=%s",
        stage, PATHS[stage], call["model"], call["provider"], meta["inputTokens"], meta["outputTokens"],
        meta["thoughtTokens"], meta["costUsd"], meta["latencyMs"], meta["attempts"],
        ",".join(f"{s['stage']}:{s['reason']}" for s in skipped) or "-",
    )
    text = call["text"]
    if meta["status"] != "completed":
        raise InvalidModelOutputError(f"the answer ended with status {meta['status']!r}", raw_text=text, meta=meta)
    try:
        converted = convert_output(text, table)
    except ValidationError as exc:
        raise InvalidModelOutputError(f"response is not valid hybrid v2 output: {exc}", raw_text=text, meta=meta) from exc
    items = converted.pop("items")
    meta.update(converted)
    return {"items": items, "meta": meta}
