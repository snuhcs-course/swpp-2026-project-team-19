"""Hybrid extraction: CLOVA OCR lines + the photo -> Gemini with the frozen hybrid prompt v1.

Same request as ai/ocr/hybrid.py (E2E, condition A2): user text = header + `<ocr_lines>`,
then the image; response schema HybridExtraction (prompt v1 output + `source_lines`).
The model and thinking level come from the extraction settings (EXTRACTION_MODEL,
EXTRACTION_THINKING_LEVEL), as for the Gemini-only extractor.

Returns the flow v2 4.3 items (same conversion as extract_menu) and a meta that keeps the
OCR line table with boxes and, per item, its source lines and their union box, so a review
screen can crop the menu line from the photo (no DB column for it yet: ai/docs/p35_backend_notes.md).
"""

import hashlib
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any, Literal, Optional

from google import genai
from pydantic import BaseModel, ValidationError

from app.extraction.clova import ClovaSettings, build_lines, call_ocr, format_lines, image_size, ocr_lines_table
from app.extraction.config import ExtractionSettings, load_settings
from app.extraction.convert import group_items, to_flow_items
from app.extraction.errors import InvalidModelOutputError
from app.extraction.gemini import build_request, call_with_retries
from app.extraction.image import prepare_image
from app.extraction.schema import ExtractionItems

PROMPT_VERSION = "hybrid-v1"
PROMPT_PATH = Path(__file__).with_name("hybrid_prompt_v1.md")
USER_HEADER = "메뉴판 사진 한 장과, 같은 사진의 OCR 줄 목록이다. 규칙에 따라 항목을 추출해."


# ---- Hybrid prompt v1 output (sent as the response schema; same names as ai/ocr/hybrid.py) ----


class SourceLines(BaseModel):
    name: list[str]
    price: list[str]


class HybridItem(BaseModel):
    raw_name: str
    price_krw: Optional[int]
    pour_ml: Optional[int]
    unit: Optional[Literal["glass", "bottle"]]
    source_lines: SourceLines


class HybridExtraction(BaseModel):
    items: list[HybridItem]


@cache
def load_prompt() -> str:
    # LF regardless of how git checked the file out, so the bytes match the E2E runs.
    return PROMPT_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")


def user_text(table: list[dict[str, Any]]) -> str:
    return f"{USER_HEADER}\n\n<ocr_lines>\n{format_lines(table)}\n</ocr_lines>"


def run_ocr(image: bytes, mime_type: str, clova: ClovaSettings, client: Any = None) -> dict[str, Any]:
    """OCR the prepared photo. Returns {"prepared", "preparedMime", "table", "ocr"}; raises ClovaOCRError."""
    prepared, prepared_mime = prepare_image(image, mime_type)
    ocr = call_ocr(clova, prepared, prepared_mime, client)
    lines = build_lines(ocr["response"])
    table = ocr_lines_table(lines, image_size(ocr["response"], tuple(ocr["sentSize"])))
    return {"prepared": prepared, "preparedMime": prepared_mime, "table": table,
            "ocr": {"latencyMs": ocr["latencyMs"], "attempts": ocr["attempts"], "sentSize": ocr["sentSize"]}}


def item_sources(hybrid_items: list[dict[str, Any]], table: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per flow item (same grouping as to_flow_items): OCR name/price line ids and their union box.

    Ids the model made up (not in the OCR table) are dropped. `box` is None without any line.
    """
    boxes = {row["id"]: row["box"] for row in table}
    out = []
    for order, group in enumerate(group_items(hybrid_items), start=1):
        name = list(dict.fromkeys(i for g in group for i in g["source_lines"]["name"] if i in boxes))
        price = list(dict.fromkeys(i for g in group for i in g["source_lines"]["price"] if i in boxes))
        ids = name + [i for i in price if i not in name]
        box = None
        if ids:
            bs = [boxes[i] for i in ids]
            box = [min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs)]
        out.append({"itemOrder": order, "nameLines": name, "priceLines": price, "box": box})
    return out


def extract_menu_hybrid(
    image: bytes,
    mime_type: str,
    clova: ClovaSettings,
    *,
    settings: ExtractionSettings | None = None,
    client: Any = None,
    ocr_client: Any = None,
) -> dict[str, Any]:
    """OCR + Gemini for one photo. Returns {"items": [...], "meta": {...}} like extract_menu.

    Raises ClovaOCRError when OCR fails (the adapter then falls back to the Gemini-only path),
    and the extract_menu errors (ModelCallError, InvalidModelOutputError, ...) after OCR.
    """
    settings = settings or load_settings()
    ocr = run_ocr(image, mime_type, clova, ocr_client)
    prompt = load_prompt()
    request = build_request(settings, prompt, ocr["prepared"], ocr["preparedMime"], HybridExtraction.model_json_schema())
    request["input"][0]["text"] = user_text(ocr["table"])

    started_at = datetime.now(UTC).isoformat()
    result = call_with_retries(settings, request, client)
    interaction = result.interaction
    usage = getattr(interaction, "usage", None)
    meta: dict[str, Any] = {
        "mode": "hybrid",
        "model": settings.model,
        "thinkingLevel": settings.thinking_level,
        "promptVersion": PROMPT_VERSION,
        "promptSha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "sdk": f"google-genai {genai.__version__}",
        "api": "interactions",
        "imageSha256": hashlib.sha256(ocr["prepared"]).hexdigest(),
        "startedAt": started_at,
        "latencyMs": result.latency_ms,
        "attempts": result.attempts,
        "status": str(getattr(interaction, "status", None)),
        "inputTokens": getattr(usage, "total_input_tokens", None),
        "outputTokens": getattr(usage, "total_output_tokens", None),
        "thoughtTokens": getattr(usage, "total_thought_tokens", None),
        "totalTokens": getattr(usage, "total_tokens", None),
        "ocr": {**ocr["ocr"], "provider": "clova-general-v2", "tableDetection": False, "lines": ocr["table"]},
        "rawOutput": None,
        "itemSources": None,
    }

    text = getattr(interaction, "output_text", None) or ""
    if meta["status"] != "completed":
        raise InvalidModelOutputError(f"interaction status is {meta['status']!r}", raw_text=text, meta=meta)
    try:
        hybrid = HybridExtraction.model_validate_json(text).model_dump()
    except ValidationError as exc:
        raise InvalidModelOutputError(f"response is not valid hybrid v1 output: {exc}", raw_text=text, meta=meta) from exc
    meta["rawOutput"] = hybrid

    v1_items = [{k: v for k, v in item.items() if k != "source_lines"} for item in hybrid["items"]]
    try:
        items = ExtractionItems.model_validate({"items": to_flow_items(v1_items)})
    except ValidationError as exc:
        raise InvalidModelOutputError(f"converted items failed validation: {exc}", raw_text=text, meta=meta) from exc
    meta["itemSources"] = item_sources(hybrid["items"], ocr["table"])
    return {"items": items.model_dump(mode="json")["items"], "meta": meta}
