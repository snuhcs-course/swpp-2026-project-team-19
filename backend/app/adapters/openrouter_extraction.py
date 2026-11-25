"""Hybrid menu extraction through OpenRouter, with the Gemini API behind it (I5-P19).

Selected with MENU_EXTRACTOR=openrouter. One CLOVA OCR call, then the route ladder of
app.extraction.routed: OpenRouter (the primary model, then its fallback models), the Gemini API
direct model, the Gemini API lite model. MENU_EXTRACTOR=gemini is unchanged and stays the way
back: it never loads this module.

The extracted items are those of HybridMenuExtractor with prompt v2: every line of the menu in
the printed order, non-whisky lines as product lines of kind `other`.

raw_output is the hybrid meta. `raw_output["route"]` says which stage, model and provider read
the photo and which stages failed before it; tokens, `costUsd` and `latencyMs` are those of the
call that answered. The run's `model_name` column is written when the photo is uploaded, before
any route is known, so it holds the primary model; the model that read the photo is
`raw_output["model"]`.

When the OCR step fails, the photo goes through the Gemini-only extractor (lite model), as it does
for HybridMenuExtractor, and `raw_output["hybridFallback"]` records why.
"""

import logging

from app import extraction
from app.adapters.extraction import ExtractionError, ExtractionResult, parse_extraction_response
from app.adapters.gemini_extraction import GeminiMenuExtractor, _message
from app.adapters.hybrid_extraction import in_menu_order
from app.extraction.clova import ClovaOCRError, ClovaSettings, load_clova_settings
from app.extraction.routed import (
    PROMPTS,
    AllRoutesFailedError,
    CircuitBreaker,
    RouteSettings,
    extract_menu_routed,
    load_route_settings,
)
from app.models import ExtractionApproach

logger = logging.getLogger(__name__)


class OpenRouterMenuExtractor:
    """One CLOVA OCR call and the first route that answers, per image. Blocking; runs in the background job."""

    approach = ExtractionApproach.OCR_LLM
    provider = "naver-clova+openrouter"

    def __init__(self, route: RouteSettings | None = None, clova: ClovaSettings | None = None,
                 breaker: CircuitBreaker | None = None) -> None:
        # Raise extraction.ExtractionConfigError when a variable is missing or invalid.
        self.route = route or load_route_settings()
        self.clova = clova or load_clova_settings()
        self.breaker = breaker or CircuitBreaker(self.route.breaker_failures, self.route.breaker_cooldown_s)
        self.model_name = self.route.openrouter.model
        self.pipeline_version = (
            f"bottlemap-menu-hybrid-prompt{PROMPTS[self.route.prompt][0]}"
            f"-reasoning-{self.route.openrouter.reasoning_effort}"
        )
        self.fallback = GeminiMenuExtractor(self.route.lite)

    def extract(self, image: bytes, content_type: str, filename: str | None) -> ExtractionResult:
        try:
            result = extract_menu_routed(image, content_type, self.clova, self.route, self.breaker)
        except ClovaOCRError as error:
            logger.warning("openrouter extraction: CLOVA OCR failed, falling back to Gemini only: %s", error)
            fallback = self.fallback.extract(image, content_type, filename)
            return ExtractionResult(items=fallback.items,
                                    raw_output={**fallback.raw_output, "hybridFallback": {"reason": str(error)}})
        except extraction.InvalidModelOutputError as error:
            raise ExtractionError(_message(error), raw_output={**error.meta, "rawText": error.raw_text}) from error
        except AllRoutesFailedError as error:
            raise ExtractionError(_message(error), raw_output={"attempts": error.attempts, "route": error.route}) from error
        except extraction.ExtractionError as error:  # UnsupportedImageError (before any call)
            raise ExtractionError(_message(error)) from error

        payload, meta = in_menu_order(result["items"], result["meta"])
        try:
            items = parse_extraction_response({"items": payload})
        except ExtractionError as error:
            raise ExtractionError(str(error), raw_output=meta) from error
        return ExtractionResult(items=items, raw_output=meta)
