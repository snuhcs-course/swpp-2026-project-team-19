"""Menu extraction from a PDF (I4-P13), on top of the hybrid extractor.

    extractor = PdfMenuExtractor()
    for page in extractor.pages(data):          # PdfError: encrypted, corrupt, empty, too long
        result = extractor.extract_page(page)   # ExtractionError, like MenuExtractor.extract

`pages` turns the file into one image per page (app.extraction.pdf), so each page can be stored
and reviewed like a menu photo. `extract_page` returns what `HybridMenuExtractor.extract` returns
for a photo, with `raw_output["pdf"]` = {"page", "kind", "textLayer"}:

- a scanned page goes through `HybridMenuExtractor.extract` unchanged (CLOVA OCR, Gemini, and
  the Gemini-only fallback when OCR fails);
- a text page skips CLOVA: its lines come from the PDF's text layer (app.extraction.pdf_hybrid)
  and `raw_output["ocr"]["provider"]` is "pdf-text-layer". There is no fallback for it, because
  no OCR call can fail; an error from the Gemini call fails the page as it does for a photo.

The upload API does not take PDFs yet: this is the part the upload calls once it does.
"""

from typing import Any

from app import extraction
from app.adapters.extraction import ExtractionError, ExtractionResult, parse_extraction_response
from app.adapters.gemini_extraction import _message
from app.adapters.hybrid_extraction import HybridMenuExtractor
from app.extraction.pdf import MAX_PDF_PAGES, PdfPage, read_pdf
from app.extraction.pdf_hybrid import TEXT_LAYER_PROVIDER, extract_pdf_page


def _pdf_meta(page: PdfPage) -> dict[str, Any]:
    return {"page": page.number, "kind": page.kind, "textLayer": page.text_layer}


class PdfMenuExtractor:
    """Pages of a PDF through the hybrid extractor. Blocking; runs in the background job."""

    def __init__(self, hybrid: HybridMenuExtractor | None = None) -> None:
        # Raises extraction.ExtractionConfigError when the hybrid extractor's settings are missing.
        self.hybrid = hybrid or HybridMenuExtractor()
        self.approach = self.hybrid.approach
        self.provider = self.hybrid.provider
        self.model_name = self.hybrid.model_name
        self.pipeline_version = f"{self.hybrid.pipeline_version}-pdf"

    def pages(self, data: bytes, *, max_pages: int = MAX_PDF_PAGES) -> list[PdfPage]:
        """Raises app.extraction.pdf.PdfError; its `code` says which kind of file it was."""
        return read_pdf(data, max_pages=max_pages)

    def extract_page(self, page: PdfPage) -> ExtractionResult:
        if page.kind == "scanned":
            try:
                result = self.hybrid.extract(page.image, page.mime_type, None)
            except ExtractionError as error:
                raw_output = {**(error.raw_output or {}), "pdf": _pdf_meta(page)}
                raise ExtractionError(str(error), raw_output=raw_output) from error
            return ExtractionResult(items=result.items, raw_output={**result.raw_output, "pdf": _pdf_meta(page)})

        def failed(meta: dict[str, Any]) -> dict[str, Any]:
            # the hybrid meta of a failed call, with where its lines came from
            ocr = {**meta.get("ocr", {}), "provider": TEXT_LAYER_PROVIDER} if "ocr" in meta else None
            return {**meta, **({"ocr": ocr} if ocr else {}), "pdf": _pdf_meta(page)}

        try:
            result = extract_pdf_page(page, None, settings=self.hybrid.settings, prompt=self.hybrid.prompt)
        except extraction.InvalidModelOutputError as error:
            raw_output = {**failed(error.meta), "rawText": error.raw_text}
            raise ExtractionError(_message(error), raw_output=raw_output) from error
        except extraction.ModelCallError as error:
            raise ExtractionError(_message(error), raw_output=failed({"attempts": error.attempts})) from error
        except extraction.ExtractionError as error:
            raise ExtractionError(_message(error), raw_output=failed({})) from error
        meta: dict[str, Any] = result["meta"]
        try:
            items = parse_extraction_response({"items": result["items"]})
        except ExtractionError as error:
            raise ExtractionError(str(error), raw_output=meta) from error
        return ExtractionResult(items=items, raw_output=meta)
