"""Menu extraction from a PDF through the route ladder of MENU_EXTRACTOR=openrouter (I5-P19 follow-up).

    extractor = pdf_extractor_for(get_menu_extractor())   # the PDF extractor of the server's extractor
    for page in extractor.pages(data):                    # PdfError: encrypted, corrupt, empty, too long
        result = extractor.extract_page(page)             # ExtractionError, like MenuExtractor.extract
    # or, under the limits of I4-P37:  extract_pdf_pages(extractor, extractor.pages(data))

`PdfMenuExtractor` (app.adapters.pdf_extraction) reads a page with the hybrid extractor: the Gemini
API, the lite model. `RoutedPdfMenuExtractor` reads it with `OpenRouterMenuExtractor` instead, so a
page takes the same routes as a photo (OpenRouter's primary model, a fallback model, the Gemini API
direct model, the lite model), shares the photo extractor's circuit breaker and daily paid budget,
and leaves the same record: `raw_output["route"]`, tokens, `costUsd`, `latencyMs`, plus
`raw_output["pdf"]` = {"page", "kind", "textLayer"} as the other PDF extractor writes it.

- a scanned page is a picture: it goes through `OpenRouterMenuExtractor.extract` unchanged (one
  CLOVA OCR call, then the ladder; the Gemini-only fallback when OCR fails), the facing-page guard
  included (app.extraction.edge_guard: a scan of an open book can show the next page's edge);
- a text page skips CLOVA: its lines come from the PDF's text layer and
  `raw_output["ocr"]["provider"]` is "pdf-text-layer". No OCR call is made for it, and the
  facing-page guard is off: a text layer holds the lines of its own page only.

`pdf_extractor_for` picks the PDF extractor that matches the server's extractor, so
MENU_EXTRACTOR=gemini with EXTRACTION_MODE=hybrid keeps `PdfMenuExtractor` exactly as it was.

The upload API does not take PDFs yet: this is the part the upload calls once it does.
"""

from dataclasses import replace
from typing import Any

from app import extraction
from app.adapters.extraction import ExtractionError, ExtractionResult, MenuExtractor
from app.adapters.hybrid_extraction import HybridMenuExtractor
from app.adapters.openrouter_extraction import OpenRouterMenuExtractor
from app.adapters.pdf_extraction import PdfMenuExtractor
from app.extraction.pdf import MAX_PDF_PAGES, PdfPage, read_pdf
from app.extraction.pdf_hybrid import _TEXT_LAYER_SETTINGS, TEXT_LAYER_PROVIDER, TextLayerOcr


def _pdf_meta(page: PdfPage) -> dict[str, Any]:
    return {"page": page.number, "kind": page.kind, "textLayer": page.text_layer}


class RoutedPdfMenuExtractor:
    """Pages of a PDF through the OpenRouter extractor's routes. Blocking; runs in the background job."""

    def __init__(self, openrouter: OpenRouterMenuExtractor | None = None) -> None:
        # Raises extraction.ExtractionConfigError when the OpenRouter extractor's settings are missing.
        self.openrouter = openrouter or OpenRouterMenuExtractor()
        self.approach = self.openrouter.approach
        self.provider = self.openrouter.provider
        self.model_name = self.openrouter.model_name
        self.pipeline_version = f"{self.openrouter.pipeline_version}-pdf"

    def pages(self, data: bytes, *, max_pages: int = MAX_PDF_PAGES) -> list[PdfPage]:
        """Raises app.extraction.pdf.PdfError; its `code` says which kind of file it was."""
        return read_pdf(data, max_pages=max_pages)

    def extract_page(self, page: PdfPage) -> ExtractionResult:
        text_page = page.kind == "text"
        try:
            if text_page:
                result = self.openrouter.extract_with(page.image, page.mime_type, _TEXT_LAYER_SETTINGS, TextLayerOcr(page),
                                                      edge_guard=False)
            else:
                result = self.openrouter.extract(page.image, page.mime_type, None)
        except ExtractionError as error:
            raise ExtractionError(str(error), raw_output=self._with_page(error.raw_output or {}, page)) from error
        return ExtractionResult(items=result.items, raw_output=self._with_page(result.raw_output, page))

    @staticmethod
    def _with_page(raw_output: dict[str, Any], page: PdfPage) -> dict[str, Any]:
        out = {**raw_output, "pdf": _pdf_meta(page)}
        if page.kind == "text" and isinstance(out.get("ocr"), dict):
            out["ocr"] = {**out["ocr"], "provider": TEXT_LAYER_PROVIDER}  # no OCR service was called
        return out

    def for_page(self, attempts: int, timeout_s: float, ocr_deadline_s: float) -> "RoutedPdfMenuExtractor":
        """This extractor with one page's limits (app.adapters.pdf_guards): `attempts` tries of the
        OpenRouter call and one try of each Gemini API route, every call cut at `timeout_s`, and the
        CLOVA call of a scanned page within `ocr_deadline_s`. The circuit breaker and the daily paid
        budget are the photo extractor's own, not copies: a PDF's pages count like photos."""
        source = self.openrouter
        limits = {"request_timeout_s": timeout_s, "wall_timeout_s": timeout_s}
        route = replace(
            source.route,
            openrouter=replace(source.route.openrouter, max_attempts=attempts, **limits),
            direct=replace(source.route.direct, max_attempts=1, **limits),
            lite=replace(source.route.lite, max_attempts=1, **limits),
        )
        half = ocr_deadline_s / 2
        clova = replace(source.clova, deadline_s=half, timeout_s=min(source.clova.timeout_s, half))
        return RoutedPdfMenuExtractor(OpenRouterMenuExtractor(route, clova, source.breaker, source.budget))


def pdf_extractor_for(extractor: MenuExtractor) -> PdfMenuExtractor | RoutedPdfMenuExtractor:
    """The PDF extractor that reads pages the way `extractor` reads photos.

    Raises extraction.ExtractionConfigError for an extractor that has no PDF path (the mock, and
    MENU_EXTRACTOR=gemini without EXTRACTION_MODE=hybrid, which reads photos without OCR lines).
    """
    if isinstance(extractor, OpenRouterMenuExtractor):
        return RoutedPdfMenuExtractor(extractor)
    if isinstance(extractor, HybridMenuExtractor):
        return PdfMenuExtractor(extractor)
    raise extraction.ExtractionConfigError(
        "PDF menus need MENU_EXTRACTOR=openrouter, or MENU_EXTRACTOR=gemini with EXTRACTION_MODE=hybrid; "
        f"got {type(extractor).__name__}"
    )
