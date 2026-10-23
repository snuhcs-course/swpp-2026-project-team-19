"""Gemini Interactions API call with the P14 retry and timeout policy (ai/extract/extract.py).

The SDK's own retries are off so `attempts` is the real number of calls. Timeouts,
connection errors and HTTP 429/5xx are retried with backoff 5, 10, 20, 40, 60 s.
Besides the SDK read timeout, every attempt has a wall-clock cap: in P14 a connection
once hung for 50+ minutes without tripping the SDK timeout.
"""

import base64
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx
from google import genai
from google.genai import types

# Same import as the P14 experiment; google-genai is pinned to 2.28.0 in pyproject.toml.
from google.genai._gaos.lib.compat_errors import APIConnectionError

from app.extraction.config import ExtractionSettings
from app.extraction.errors import ModelCallError

logger = logging.getLogger(__name__)

USER_TEXT = "이 메뉴판 사진에서 규칙에 따라 항목을 추출해."
RETRY_STATUS = {429, 500, 502, 503, 504}

# Replaced in tests so retries do not wait.
sleep = time.sleep


class HardTimeout(Exception):
    pass


@dataclass(frozen=True)
class CallResult:
    interaction: Any
    attempts: int
    latency_ms: int


def make_client(settings: ExtractionSettings) -> genai.Client:
    return genai.Client(
        api_key=settings.api_key,
        http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)),
    )


def build_request(
    settings: ExtractionSettings, prompt: str, image: bytes, mime_type: str, response_schema: dict
) -> dict[str, Any]:
    return dict(
        model=settings.model,
        system_instruction=prompt,
        input=[
            {"type": "text", "text": USER_TEXT},
            {"type": "image", "data": base64.b64encode(image).decode("ascii"), "mime_type": mime_type},
        ],
        response_format={"type": "text", "mime_type": "application/json", "schema": response_schema},
        generation_config={"thinking_level": settings.thinking_level},
        store=False,
    )


def call_with_retries(settings: ExtractionSettings, request: dict[str, Any], client: Any = None) -> CallResult:
    """Send the request; retry transient failures. The latency is that of the successful attempt."""
    client = client or make_client(settings)
    attempts = 0
    while True:
        attempts += 1
        t0 = time.perf_counter()
        try:
            interaction = _create_with_deadline(client, request, settings)
            break
        except Exception as exc:
            if not _is_transient(exc):
                raise ModelCallError(f"{type(exc).__name__}: {exc}", attempts=attempts) from exc
            if attempts >= settings.max_attempts:
                raise ModelCallError(
                    f"gave up after {attempts} attempts; last error {type(exc).__name__}: {exc}", attempts=attempts
                ) from exc
            wait = min(60, 5 * 2 ** (attempts - 1))
            logger.warning(
                "extraction retry %d/%d after %s: %.120s (wait %ds)",
                attempts, settings.max_attempts - 1, type(exc).__name__, exc, wait,
            )
            if isinstance(exc, HardTimeout):
                client = make_client(settings)  # don't reuse a client holding a hung connection
            sleep(wait)
    return CallResult(interaction, attempts, round((time.perf_counter() - t0) * 1000))


def _create_with_deadline(client: Any, request: dict[str, Any], settings: ExtractionSettings) -> Any:
    """interactions.create with a hard wall-clock limit. A hung call is abandoned in its daemon thread."""
    box: dict[str, Any] = {}

    def run() -> None:
        try:
            box["result"] = client.interactions.create(**request, timeout=settings.request_timeout_s)
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


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, (HardTimeout, APIConnectionError, httpx.TimeoutException, httpx.NetworkError)):
        return True
    return _status_code(exc) in RETRY_STATUS


def _status_code(exc: Exception) -> int | None:
    for attr in ("code", "status_code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    return None
