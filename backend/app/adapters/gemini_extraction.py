"""Menu extraction with Gemini: connects `app.extraction.extract_menu` (A4) to `MenuExtractor`.

Settings are read when the extractor is created, so a missing key or model fails at server
start rather than on the first upload. Every A4 exception becomes the adapter's
`ExtractionError`, prefixed with the A4 class name because processing records only the
adapter class (`raw_output.error`).
"""

from typing import Any

from app import extraction
from app.adapters.extraction import ExtractionError, ExtractionResult, parse_extraction_response
from app.extraction.service import PROMPT_VERSION
from app.models import ExtractionApproach


class GeminiMenuExtractor:
    """Calls the vision LLM once per image (with A4's retries). Blocking; runs in the background job.

    raw_output on success is A4's `meta` as is: the model's v1 output before conversion,
    model ID, thinking level, prompt hash, tokens, latency and attempts.
    """

    approach = ExtractionApproach.VISION_LLM
    provider = "google"

    def __init__(self, settings: extraction.ExtractionSettings | None = None) -> None:
        # Raises extraction.ExtractionConfigError when an environment variable is missing or invalid.
        self.settings = settings or extraction.load_settings()
        self.model_name = self.settings.model
        self.pipeline_version = f"bottlemap-menu-gemini-prompt{PROMPT_VERSION}-thinking-{self.settings.thinking_level}"

    def extract(self, image: bytes, content_type: str, filename: str | None) -> ExtractionResult:
        # filename is part of the protocol for the mock; the real extractor reads only the image.
        try:
            result = extraction.extract_menu(image, content_type, settings=self.settings)
        except extraction.InvalidModelOutputError as error:
            raise ExtractionError(_message(error), raw_output={**error.meta, "rawText": error.raw_text}) from error
        except extraction.ModelCallError as error:
            raise ExtractionError(_message(error), raw_output={"attempts": error.attempts}) from error
        except extraction.ExtractionError as error:  # ExtractionConfigError, UnsupportedImageError
            raise ExtractionError(_message(error)) from error

        meta: dict[str, Any] = result["meta"]
        try:
            items = parse_extraction_response({"items": result["items"]})
        except ExtractionError as error:
            raise ExtractionError(str(error), raw_output=meta) from error
        return ExtractionResult(items=items, raw_output=meta)


def _message(error: Exception) -> str:
    return f"{type(error).__name__}: {error}"
