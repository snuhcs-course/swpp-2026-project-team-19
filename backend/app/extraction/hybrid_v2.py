"""Hybrid extraction with prompt v2 (I4-P12): every menu line carries a category.

Prompt v1 leaves non-whisky sections out. Prompt v2 returns them too and tags each item
`whisky`, `cocktail`, `food` or `other` by its section title. The category rules are the v1
exclusion rules turned into labels, so the `whisky` items are the items v1 returns.

Whisky items take the v1 path unchanged: flow v2 4.3 items, stored as extracted_items and sent
to product matching. The other items never become flow items, so they are not stored as
extracted_items and cannot reach product matching. They are kept in the meta (the run's
raw_output) under `otherItems`, with their name, price options, category and source box, for the
menu features that will store non-whisky lines.

hybrid.py and hybrid_prompt_v1.md are frozen for the I3 evaluation (ai/docs/i3_eval_freeze.md),
so v2 lives in this module and imports what it shares with v1.
"""

import hashlib
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any, Literal

from google import genai
from pydantic import BaseModel, ValidationError

from app.extraction.clova import ClovaSettings
from app.extraction.config import ExtractionSettings, load_settings
from app.extraction.convert import group_items, to_flow_items
from app.extraction.errors import InvalidModelOutputError
from app.extraction.gemini import build_request, call_with_retries
from app.extraction.hybrid import HybridItem, item_sources, run_ocr, user_text
from app.extraction.schema import MAX_TEXT, ExtractedOption, ExtractionItems

PROMPT_VERSION = "hybrid-v2"
PROMPT_PATH = Path(__file__).with_name("hybrid_prompt_v2.md")
WHISKY = "whisky"
Category = Literal["whisky", "cocktail", "food", "other"]


class HybridItemV2(HybridItem):
    category: Category


class HybridExtractionV2(BaseModel):
    items: list[HybridItemV2]


@cache
def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").replace("\r\n", "\n")


def line_groups(hybrid_items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """The rows of each menu line, in output order: one row, or a glass row and a bottle row.

    Grouped over the whole answer, before whisky and non-whisky rows are separated. Grouping the
    separated lists instead would pair a glass row with a bottle row of the same name that had
    another line between them, which convert.group_items never does.
    """
    groups: list[list[dict[str, Any]]] = []
    for same_category in _runs(hybrid_items):
        groups += group_items(same_category)
    return groups


def _runs(hybrid_items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Consecutive rows of one category."""
    runs: list[list[dict[str, Any]]] = []
    for item in hybrid_items:
        if runs and runs[-1][0]["category"] == item["category"]:
            runs[-1].append(item)
        else:
            runs.append([item])
    return runs


def _plain(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in row.items() if k not in ("source_lines", "category")} for row in rows]


def other_items(hybrid_items: list[dict[str, Any]], table: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """The non-whisky items in output order, and how many were dropped as unusable.

    Glass and bottle rows of one line are grouped as for whisky. An item whose name or options
    break the stored limits is dropped instead of failing the photo: these lines are extra, and
    one bad cocktail must not cost the owner the whisky lines.
    """
    out: list[dict[str, Any]] = []
    dropped = 0
    for group in line_groups(hybrid_items):
        if group[0]["category"] == WHISKY:
            continue
        [flow], [source] = to_flow_items(_plain(group)), item_sources(group, table)
        name = flow["rawText"].strip()
        try:
            options = [ExtractedOption.model_validate(o).model_dump() for o in flow["options"]]
        except ValidationError:
            dropped += 1
            continue
        if not 1 <= len(name) <= MAX_TEXT:
            dropped += 1
            continue
        out.append({"itemOrder": len(out) + 1, "rawText": name, "category": group[0]["category"], "options": options,
                    "nameLines": source["nameLines"], "priceLines": source["priceLines"], "box": source["box"]})
    return out, dropped


def convert_output(text: str, table: list[dict[str, Any]]) -> dict[str, Any]:
    """The model's answer -> {"items", "rawOutput", "itemSources", "otherItems", "otherItemsDropped"}.

    `items` are the flow v2 4.3 items of the whisky lines only. Raises pydantic.ValidationError
    when the answer is not prompt v2 output or a whisky line fails the flow validation.
    """
    hybrid = HybridExtractionV2.model_validate_json(text).model_dump()
    whisky = [group for group in line_groups(hybrid["items"]) if group[0]["category"] == WHISKY]
    flow_items = [{**to_flow_items(_plain(group))[0], "itemOrder": order} for order, group in enumerate(whisky, start=1)]
    sources = [{**item_sources(group, table)[0], "itemOrder": order} for order, group in enumerate(whisky, start=1)]
    items = ExtractionItems.model_validate({"items": flow_items})
    others, dropped = other_items(hybrid["items"], table)
    return {"items": items.model_dump(mode="json")["items"], "rawOutput": hybrid,
            "itemSources": sources, "otherItems": others, "otherItemsDropped": dropped}


def extract_menu_hybrid_v2(
    image: bytes,
    mime_type: str,
    clova: ClovaSettings,
    *,
    settings: ExtractionSettings | None = None,
    client: Any = None,
    ocr_client: Any = None,
) -> dict[str, Any]:
    """OCR + Gemini for one photo with prompt v2. Same return shape and errors as extract_menu_hybrid;
    the meta also has `otherItems` and `otherItemsDropped`."""
    settings = settings or load_settings()
    ocr = run_ocr(image, mime_type, clova, ocr_client)
    prompt = load_prompt()
    request = build_request(settings, prompt, ocr["prepared"], ocr["preparedMime"],
                            HybridExtractionV2.model_json_schema())
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
        "otherItems": None,
        "otherItemsDropped": None,
    }

    text = getattr(interaction, "output_text", None) or ""
    if meta["status"] != "completed":
        raise InvalidModelOutputError(f"interaction status is {meta['status']!r}", raw_text=text, meta=meta)
    try:
        converted = convert_output(text, ocr["table"])
    except ValidationError as exc:
        raise InvalidModelOutputError(f"response is not valid hybrid v2 output: {exc}", raw_text=text, meta=meta) from exc
    items = converted.pop("items")
    meta.update(converted)
    return {"items": items, "meta": meta}
