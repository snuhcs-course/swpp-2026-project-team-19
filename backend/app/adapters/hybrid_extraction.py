"""Hybrid menu extraction (CLOVA OCR + Gemini, hybrid prompt v1 or v2) behind `MenuExtractor`.

Selected with MENU_EXTRACTOR=gemini and EXTRACTION_MODE=hybrid (default EXTRACTION_MODE=gemini
keeps the Gemini-only extractor). When the OCR step fails, the photo goes through the
Gemini-only extractor instead and the fallback is logged and recorded in raw_output
(`hybridFallback`). Errors after a successful OCR (Gemini call, invalid output) are not
retried on the other path: they fail the run like the Gemini-only extractor does.

EXTRACTION_HYBRID_PROMPT picks the prompt: v1 (default, the frozen prompt) or v2 (I4-P12), which
also reads non-whisky lines. With v2 the extracted items are every line of the menu in the
printed order: the whisky lines, and the non-whisky lines as product lines of kind `other`
(API spec 5.4, flow doc 4.3), which are stored and reviewed but not matched. raw_output keeps
`otherItems` as the extraction gave them, with each line's category (cocktail, food, other).
"""

import logging
import os
from typing import Any

from app import extraction
from app.adapters.extraction import ExtractionError, ExtractionResult, parse_extraction_response
from app.adapters.gemini_extraction import GeminiMenuExtractor, _message
from app.extraction.clova import ClovaOCRError, ClovaSettings, load_clova_settings
from app.extraction.hybrid import PROMPT_VERSION, extract_menu_hybrid
from app.extraction.hybrid_v2 import PROMPT_VERSION as PROMPT_VERSION_V2
from app.extraction.hybrid_v2 import extract_menu_hybrid_v2
from app.models import ExtractionApproach

logger = logging.getLogger(__name__)

_SOURCE_KEYS = ("nameLines", "priceLines", "box")

PROMPT_VERSIONS = {"v1": PROMPT_VERSION, "v2": PROMPT_VERSION_V2}


class HybridMenuExtractor:
    """One CLOVA OCR call and one Gemini call per image. Blocking; runs in the background job.

    raw_output on success is the hybrid meta: model output with source lines, OCR line table
    (ids, 0-1000 boxes, text), per-item source lines and box (`itemSources`), tokens, latency.
    """

    approach = ExtractionApproach.OCR_LLM
    provider = "naver-clova+google"

    def __init__(self, settings: extraction.ExtractionSettings | None = None,
                 clova: ClovaSettings | None = None, prompt: str | None = None) -> None:
        # Raise extraction.ExtractionConfigError when a variable is missing or invalid.
        self.settings = settings or extraction.load_settings()
        self.clova = clova or load_clova_settings()
        self.prompt = prompt or os.getenv("EXTRACTION_HYBRID_PROMPT") or "v1"
        if self.prompt not in PROMPT_VERSIONS:
            raise extraction.ExtractionConfigError(
                f"EXTRACTION_HYBRID_PROMPT must be one of {', '.join(PROMPT_VERSIONS)}, got {self.prompt!r}"
            )
        self.model_name = self.settings.model
        self.pipeline_version = (
            f"bottlemap-menu-hybrid-prompt{PROMPT_VERSIONS[self.prompt]}-thinking-{self.settings.thinking_level}"
        )
        self.fallback = GeminiMenuExtractor(self.settings)

    def extract(self, image: bytes, content_type: str, filename: str | None) -> ExtractionResult:
        extract = extract_menu_hybrid_v2 if self.prompt == "v2" else extract_menu_hybrid
        try:
            result = extract(image, content_type, self.clova, settings=self.settings)
        except ClovaOCRError as error:
            logger.warning("hybrid extraction: CLOVA OCR failed, falling back to Gemini only: %s", error)
            fallback = self.fallback.extract(image, content_type, filename)
            return ExtractionResult(items=fallback.items,
                                    raw_output={**fallback.raw_output, "hybridFallback": {"reason": str(error)}})
        except extraction.InvalidModelOutputError as error:
            raise ExtractionError(_message(error), raw_output={**error.meta, "rawText": error.raw_text}) from error
        except extraction.ModelCallError as error:
            raise ExtractionError(_message(error), raw_output={"attempts": error.attempts}) from error
        except extraction.ExtractionError as error:  # UnsupportedImageError (before any call)
            raise ExtractionError(_message(error)) from error

        payload, meta = in_menu_order(result["items"], result["meta"])
        try:
            items = parse_extraction_response({"items": payload})
        except ExtractionError as error:
            raise ExtractionError(str(error), raw_output=meta) from error
        return ExtractionResult(items=items, raw_output=meta)


def in_menu_order(items: list[dict[str, Any]], meta: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The whisky items and the non-whisky lines of a prompt v2 result as one list in menu order.

    Prompt v2 gives the whisky lines as `items` and the other lines in the meta as `otherItems`,
    each numbered from 1, with `menuOrder` saying where a line stands among all of them
    (hybrid_v2.convert_output). This puts them back together: a non-whisky line becomes a product
    line of kind `other` with its name and price options, the lines are numbered again in menu
    order, and `itemSources` is rewritten to the new numbers and gains the other lines' boxes, so
    the review screen shows every line where it is on the photo.

    A result without `otherItems` (prompt v1, or a menu of whisky only) is returned as it is. A
    line without `menuOrder` (a result recorded before it existed) goes after the lines that have
    one, in the order given.
    """
    others = meta.get("otherItems")
    if not others:
        return items, meta
    sources = {source["itemOrder"]: source for source in meta.get("itemSources") or []}
    lines: list[tuple[dict[str, Any], dict[str, Any] | None]] = [(item, sources.get(item["itemOrder"])) for item in items]
    lines += [({
        "rawText": other["rawText"], "lineType": "product", "productName": other["rawText"], "brandText": None,
        "ageYears": None, "editionName": None, "abv": None, "options": other["options"], "confidence": None,
        "kind": "other",
    }, other) for other in others]
    # sorted() is stable: lines without menuOrder keep the order given, after the others
    lines.sort(key=lambda line: (line[1] or {}).get("menuOrder") or float("inf"))
    payload, merged = [], []
    for order, (item, source) in enumerate(lines, start=1):
        payload.append({**item, "itemOrder": order})
        if source is not None:
            merged.append({"itemOrder": order, **{key: source.get(key) for key in _SOURCE_KEYS},
                           "menuOrder": source.get("menuOrder")})
    return payload, {**meta, "itemSources": merged}
