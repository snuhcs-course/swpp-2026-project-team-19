# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-06, PR #10). Reviewed by Jinwoo Park.
"""extract_menu: one menu photo -> flow v2 4.3 items plus call metadata. No DB access."""

import hashlib
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any

from google import genai
from pydantic import ValidationError

from app.extraction.config import ExtractionSettings, load_settings
from app.extraction.convert import to_flow_items
from app.extraction.errors import InvalidModelOutputError
from app.extraction.gemini import build_request, call_with_retries
from app.extraction.image import prepare_image
from app.extraction.schema import ExtractionItems, MenuExtraction

PROMPT_VERSION = "v1"
PROMPT_PATH = Path(__file__).with_name(f"prompt_{PROMPT_VERSION}.md")


@cache
def load_prompt() -> str:
    # LF regardless of how git checked the file out, so the bytes match P14.
    return PROMPT_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")


def extract_menu(
    image: bytes,
    mime_type: str,
    *,
    settings: ExtractionSettings | None = None,
    client: Any = None,
) -> dict[str, Any]:
    """Extract menu items from one photo.

    Returns {"items": [...], "meta": {...}}. `items` follows flow v2 4.3; with prompt v1
    every item is a `product` and brandText, ageYears, editionName, abv and confidence
    are null. `meta.rawOutput` is the model's v1 output before conversion.

    Blocking; with retries it can take several minutes, so call it from a background job.

    Raises (all subclasses of ExtractionError):
        ExtractionConfigError: environment variables are missing or invalid
        UnsupportedImageError: not a readable JPEG/PNG matching `mime_type`
        ModelCallError: API error, or retries ran out
        InvalidModelOutputError: the answer is not valid JSON or fails validation
    """
    settings = settings or load_settings()
    prompt = load_prompt()
    prepared, prepared_mime = prepare_image(image, mime_type)
    request = build_request(settings, prompt, prepared, prepared_mime, MenuExtraction.model_json_schema())

    started_at = datetime.now(UTC).isoformat()
    result = call_with_retries(settings, request, client)
    interaction = result.interaction
    usage = getattr(interaction, "usage", None)
    meta: dict[str, Any] = {
        "model": settings.model,
        "thinkingLevel": settings.thinking_level,
        "promptVersion": PROMPT_VERSION,
        "promptSha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "sdk": f"google-genai {genai.__version__}",
        "api": "interactions",
        "imageSha256": hashlib.sha256(prepared).hexdigest(),
        "startedAt": started_at,
        "latencyMs": result.latency_ms,
        "attempts": result.attempts,
        "status": str(getattr(interaction, "status", None)),
        "inputTokens": getattr(usage, "total_input_tokens", None),
        "outputTokens": getattr(usage, "total_output_tokens", None),
        "thoughtTokens": getattr(usage, "total_thought_tokens", None),
        "totalTokens": getattr(usage, "total_tokens", None),
        "rawOutput": None,
    }

    text = getattr(interaction, "output_text", None) or ""
    if meta["status"] != "completed":
        raise InvalidModelOutputError(f"interaction status is {meta['status']!r}", raw_text=text, meta=meta)
    try:
        v1 = MenuExtraction.model_validate_json(text).model_dump()
    except ValidationError as exc:
        raise InvalidModelOutputError(f"response is not valid v1 output: {exc}", raw_text=text, meta=meta) from exc
    meta["rawOutput"] = v1

    try:
        items = ExtractionItems.model_validate({"items": to_flow_items(v1["items"])})
    except ValidationError as exc:
        raise InvalidModelOutputError(f"converted items failed validation: {exc}", raw_text=text, meta=meta) from exc
    return {"items": items.model_dump(mode="json")["items"], "meta": meta}
