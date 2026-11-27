"""OpenRouter chat completion for menu extraction (I5-P19), with the retry policy of gemini.py.

The request is the one the 2026-11-21 and 2026-11-25 evaluations sent (ai/eval/i5_model_ladder.py):
system = the prompt, user = the OCR lines text and then the image, the response schema as a
strict json_schema, `reasoning.effort`, `max_tokens` (answer and reasoning together), and
`provider: {data_collection: "deny", require_parameters: true}` so the photo only goes to
providers that do not keep inputs and that honour the schema and the reasoning setting.

`model` is the primary model. `models` lists the fallback models: OpenRouter itself moves on to
them when every provider of the primary fails, and the answer's `model` says which one ran.

Timeouts, connection errors and HTTP 408/429/5xx are retried with backoff 5, 10, 20, 40, 60 s,
and every attempt has a wall-clock cap, as in gemini.py. OpenRouter can also answer HTTP 200 with
an `error` object in the body (a provider failed after the headers were sent); that error's code
is treated like the HTTP status. HTTP 402 (the account or the key is out of credits) is
`OpenRouterCreditError` and is never retried: waiting does not bring credits back.
"""

import base64
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.extraction.config import _positive
from app.extraction.errors import ExtractionConfigError, ModelCallError

logger = logging.getLogger(__name__)

URL = "https://openrouter.ai/api/v1/chat/completions"
RETRY_STATUS = {408, 429, 500, 502, 503, 504, 524, 529}
PAYMENT_REQUIRED = 402
REASONING_EFFORTS = ("minimal", "low", "medium", "high")

# Replaced in tests so retries do not wait.
sleep = time.sleep


class OpenRouterCreditError(ModelCallError):
    """HTTP 402: the OpenRouter account or key has no credits left (or reached its spending limit)."""


class HardTimeout(Exception):
    pass


class _Transient(Exception):
    """An answer that is worth another attempt (HTTP 408/429/5xx, or no choices in the body)."""


@dataclass(frozen=True)
class OpenRouterSettings:
    api_key: str
    model: str
    fallback_models: tuple[str, ...] = ()
    reasoning_effort: str = "medium"
    max_tokens: int = 48000
    max_attempts: int = 6
    request_timeout_s: float = 300
    wall_timeout_s: float = 330

    def __repr__(self) -> str:  # keep the key out of logs and tracebacks
        return (
            f"OpenRouterSettings(model={self.model!r}, fallback_models={self.fallback_models!r}, "
            f"reasoning_effort={self.reasoning_effort!r}, max_tokens={self.max_tokens}, "
            f"max_attempts={self.max_attempts}, request_timeout_s={self.request_timeout_s}, "
            f"wall_timeout_s={self.wall_timeout_s})"
        )


def load_openrouter_settings() -> OpenRouterSettings:
    """Read the OpenRouter settings from the environment; raise ExtractionConfigError if anything is wrong."""
    required = ("OPENROUTER_API_KEY", "OPENROUTER_EXTRACTION_MODEL")
    missing = [name for name in required if not os.getenv(name)]
    if missing:
        raise ExtractionConfigError(f"Missing required extraction environment variables: {', '.join(missing)}")
    effort = os.getenv("OPENROUTER_REASONING_EFFORT") or OpenRouterSettings.reasoning_effort
    if effort not in REASONING_EFFORTS:
        raise ExtractionConfigError(
            f"OPENROUTER_REASONING_EFFORT must be one of {', '.join(REASONING_EFFORTS)}, got {effort!r}"
        )
    model = os.environ["OPENROUTER_EXTRACTION_MODEL"]
    fallbacks = tuple(m.strip() for m in (os.getenv("OPENROUTER_FALLBACK_MODELS") or "").split(",") if m.strip())
    if model in fallbacks:
        raise ExtractionConfigError(f"OPENROUTER_FALLBACK_MODELS must not repeat OPENROUTER_EXTRACTION_MODEL ({model})")
    return OpenRouterSettings(
        api_key=os.environ["OPENROUTER_API_KEY"],
        model=model,
        fallback_models=fallbacks,
        reasoning_effort=effort,
        max_tokens=_positive("OPENROUTER_MAX_TOKENS", OpenRouterSettings.max_tokens, int),
        max_attempts=_positive("EXTRACTION_MAX_ATTEMPTS", OpenRouterSettings.max_attempts, int),
        request_timeout_s=_positive("EXTRACTION_REQUEST_TIMEOUT_S", OpenRouterSettings.request_timeout_s, float),
        wall_timeout_s=_positive("EXTRACTION_WALL_TIMEOUT_S", OpenRouterSettings.wall_timeout_s, float),
    )


def strict_schema(node: Any) -> Any:
    """The pydantic schema with `additionalProperties: false` on every object (strict json_schema)."""
    if isinstance(node, dict):
        node = {key: strict_schema(value) for key, value in node.items()}
        if node.get("type") == "object":
            node["additionalProperties"] = False
        return node
    return [strict_schema(value) for value in node] if isinstance(node, list) else node


def build_body(
    settings: OpenRouterSettings, prompt: str, user_text: str, image: bytes, mime_type: str, response_schema: dict
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": [
                {"type": "text", "text": user_text},
                {"type": "image_url", "image_url": {
                    "url": f"data:{mime_type};base64,{base64.b64encode(image).decode('ascii')}"}},
            ]},
        ],
        "response_format": {"type": "json_schema", "json_schema": {
            "name": "menu_extraction", "strict": True, "schema": strict_schema(response_schema)}},
        "reasoning": {"effort": settings.reasoning_effort},
        "max_tokens": settings.max_tokens,
        "provider": {"data_collection": "deny", "require_parameters": True},
        "usage": {"include": True},
    }
    if settings.fallback_models:
        body["models"] = list(settings.fallback_models)
    return body


@dataclass(frozen=True)
class CallResult:
    data: dict[str, Any]
    attempts: int
    latency_ms: int


def call_with_retries(settings: OpenRouterSettings, body: dict[str, Any], client: Any = None) -> CallResult:
    """Send the request; retry transient failures. The latency is that of the successful attempt.

    Raises OpenRouterCreditError on HTTP 402 and ModelCallError on any other failure that is not
    transient or that outlasts the retries.

    An attempt sent and given up before its answer may still be billed: one given up at the
    wall-clock cap (HardTimeout) is abandoned, not cancelled, and its POST goes on in its thread;
    one cut at the read timeout (httpx.ReadTimeout) closed the connection, but OpenRouter may have
    started the generation. The error then carries `abandoned_attempts` (how many such attempts),
    so the caller keeps the photo's place in the daily paid budget.
    """
    attempts = abandoned = 0
    while True:
        attempts += 1
        t0 = time.perf_counter()
        try:
            data = _checked(_post_with_deadline(client or httpx, body, settings))
            break
        except ModelCallError as exc:  # raised by _checked without the attempt count
            raise _with_abandoned(type(exc)(str(exc), attempts=attempts), abandoned) from exc
        except (_Transient, HardTimeout, httpx.TimeoutException, httpx.NetworkError) as exc:
            abandoned += isinstance(exc, (HardTimeout, httpx.ReadTimeout))
            if attempts >= settings.max_attempts:
                raise _with_abandoned(ModelCallError(
                    f"gave up after {attempts} attempts; last error {type(exc).__name__}: {exc}", attempts=attempts
                ), abandoned) from exc
            wait = min(60, 5 * 2 ** (attempts - 1))
            logger.warning(
                "openrouter retry %d/%d after %s: %.120s (wait %ds)",
                attempts, settings.max_attempts - 1, type(exc).__name__, exc, wait,
            )
            sleep(wait)
    return CallResult(data, attempts, round((time.perf_counter() - t0) * 1000))


def _with_abandoned(error: ModelCallError, abandoned: int) -> ModelCallError:
    if abandoned:
        error.abandoned_attempts = abandoned
    return error


def _post_with_deadline(client: Any, body: dict[str, Any], settings: OpenRouterSettings) -> Any:
    """POST with a hard wall-clock limit. A hung call is abandoned in its daemon thread."""
    box: dict[str, Any] = {}

    def run() -> None:
        try:
            box["result"] = client.post(
                URL, json=body, timeout=settings.request_timeout_s,
                headers={"Authorization": f"Bearer {settings.api_key}", "X-Title": "bottlemap-menu-extraction"},
            )
        except BaseException as exc:  # handed to the caller
            box["error"] = exc

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(settings.wall_timeout_s)
    if worker.is_alive():
        raise HardTimeout(f"no response within {settings.wall_timeout_s}s")
    if "error" in box:
        raise box["error"]
    return box["result"]


def _checked(response: Any) -> dict[str, Any]:
    """The JSON body of a usable answer. Raises _Transient, OpenRouterCreditError or ModelCallError."""
    try:
        data = response.json()
    except ValueError:
        data = None
    if not isinstance(data, dict):
        _fail(response.status_code if response.status_code != 200 else 502,
              f"HTTP {response.status_code}, not a JSON object: {str(getattr(response, 'text', ''))[:200]}")
    error = data.get("error")
    if response.status_code != 200 or error:
        _fail(response.status_code if response.status_code != 200 else _code(error), _describe(response, error))
    choices = data.get("choices")
    if not choices:
        raise _Transient("HTTP 200 without choices")
    if choices[0].get("finish_reason") == "error":
        error = choices[0].get("error")
        _fail(_code(error), _describe(response, error))
    return data


def _code(error: Any) -> int:
    code = error.get("code") if isinstance(error, dict) else None
    return code if isinstance(code, int) else 502


def _describe(response: Any, error: Any) -> str:
    message = error.get("message") if isinstance(error, dict) else error
    return f"HTTP {response.status_code}: {str(message)[:300]}"


def _fail(status: int, message: str) -> None:
    if status == PAYMENT_REQUIRED:
        raise OpenRouterCreditError(message, attempts=0)
    if status in RETRY_STATUS:
        raise _Transient(message)
    raise ModelCallError(message, attempts=0)


def answer(data: dict[str, Any]) -> dict[str, Any]:
    """What the extraction reads from a checked body: the text, why it ended, who answered, usage and cost."""
    choice, usage = data["choices"][0], data.get("usage") or {}
    details = usage.get("completion_tokens_details") or {}
    return {
        "text": (choice.get("message") or {}).get("content") or "",
        "finishReason": choice.get("finish_reason"),
        "model": data.get("model"),
        "provider": data.get("provider"),
        "generationId": data.get("id"),
        "inputTokens": usage.get("prompt_tokens"),
        "outputTokens": usage.get("completion_tokens"),
        "thoughtTokens": details.get("reasoning_tokens"),
        "totalTokens": usage.get("total_tokens"),
        "costUsd": usage.get("cost"),
    }
