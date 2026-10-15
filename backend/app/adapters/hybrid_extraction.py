# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-15, P35). Reviewed by Jinwoo Park.
"""Hybrid menu extraction (CLOVA OCR + Gemini, frozen hybrid prompt v1) behind `MenuExtractor`.

Selected with MENU_EXTRACTOR=gemini and EXTRACTION_MODE=hybrid (default EXTRACTION_MODE=gemini
keeps the Gemini-only extractor). When the OCR step fails, the photo goes through the
Gemini-only extractor instead and the fallback is logged and recorded in raw_output
(`hybridFallback`). Errors after a successful OCR (Gemini call, invalid output) are not
retried on the other path: they fail the run like the Gemini-only extractor does.
"""

import logging
from typing import Any

from app import extraction
from app.adapters.extraction import ExtractionError, ExtractionResult, parse_extraction_response
from app.adapters.gemini_extraction import GeminiMenuExtractor, _message
from app.extraction.clova import ClovaOCRError, ClovaSettings, load_clova_settings
from app.extraction.hybrid import PROMPT_VERSION, extract_menu_hybrid
from app.models import ExtractionApproach

logger = logging.getLogger(__name__)


class HybridMenuExtractor:
    """One CLOVA OCR call and one Gemini call per image. Blocking; runs in the background job.

    raw_output on success is the hybrid meta: model output with source lines, OCR line table
    (ids, 0-1000 boxes, text), per-item source lines and box (`itemSources`), tokens, latency.
    """

    approach = ExtractionApproach.OCR_LLM
    provider = "naver-clova+google"

    def __init__(self, settings: extraction.ExtractionSettings | None = None,
                 clova: ClovaSettings | None = None) -> None:
        # Raise extraction.ExtractionConfigError when a variable is missing or invalid.
        self.settings = settings or extraction.load_settings()
        self.clova = clova or load_clova_settings()
        self.model_name = self.settings.model
        self.pipeline_version = f"bottlemap-menu-hybrid-prompt{PROMPT_VERSION}-thinking-{self.settings.thinking_level}"
        self.fallback = GeminiMenuExtractor(self.settings)

    def extract(self, image: bytes, content_type: str, filename: str | None) -> ExtractionResult:
        try:
            result = extract_menu_hybrid(image, content_type, self.clova, settings=self.settings)
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

        meta: dict[str, Any] = result["meta"]
        try:
            items = parse_extraction_response({"items": result["items"]})
        except ExtractionError as error:
            raise ExtractionError(str(error), raw_output=meta) from error
        return ExtractionResult(items=items, raw_output=meta)
