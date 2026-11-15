"""Hybrid extraction of one PDF page (I4-P13).

A "scanned" page is a picture: it goes through `extract_menu_hybrid` (or v2) like a photo, with
a CLOVA OCR call. A "text" page goes through the same function, but the OCR step is answered
from the page's own text layer instead of CLOVA: the hybrid functions take the HTTP client of
the OCR call as `ocr_client`, and `TextLayerOcr` is such a client that returns the text layer in
CLOVA's answer format (app.extraction.pdf.clova_response). So the prompt, the request to Gemini,
the conversion to items and the line boxes are exactly those of a photo, and the frozen
extraction files are not changed.

The result is the hybrid result with two additions to `meta`:
- `meta["pdf"]`: {"page", "kind", "textLayer"} of the page
- on a text page, `meta["ocr"]["provider"]` is "pdf-text-layer" (no OCR service was called)
"""

from typing import Any

from app.extraction.clova import ClovaSettings
from app.extraction.config import ExtractionSettings
from app.extraction.hybrid import extract_menu_hybrid
from app.extraction.hybrid_v2 import extract_menu_hybrid_v2
from app.extraction.pdf import PdfPage, clova_response

TEXT_LAYER_PROVIDER = "pdf-text-layer"
# What the OCR step gets on a text page. No request leaves the process: `TextLayerOcr` answers it.
# One attempt and no deadline, so the step is a single `post` on the client.
_TEXT_LAYER_SETTINGS = ClovaSettings(invoke_url="pdf-text-layer://page", secret="", max_attempts=1, deadline_s=None)

_EXTRACT = {"v1": extract_menu_hybrid, "v2": extract_menu_hybrid_v2}


class _Answer:
    status_code = 200

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class TextLayerOcr:
    """Stands in for the HTTP client of the OCR call and answers with the page's text layer."""

    def __init__(self, page: PdfPage) -> None:
        if page.kind != "text":
            raise ValueError(f"page {page.number} has no usable text layer ({page.text_layer})")
        self._payload = clova_response(page)

    def post(self, url: str, **kwargs: Any) -> _Answer:
        return _Answer(self._payload)


def extract_pdf_page(
    page: PdfPage,
    clova: ClovaSettings | None,
    *,
    settings: ExtractionSettings | None = None,
    prompt: str = "v1",
    client: Any = None,
    ocr_client: Any = None,
) -> dict[str, Any]:
    """Extract the menu of one page. Returns {"items", "meta"} like `extract_menu_hybrid`.

    `clova` is needed for a scanned page only. Raises what the hybrid extraction raises:
    ClovaOCRError when the OCR of a scanned page fails, and the extraction errors after that.
    """
    extract = _EXTRACT[prompt]
    if page.kind == "text":
        result = extract(page.image, page.mime_type, _TEXT_LAYER_SETTINGS, settings=settings, client=client,
                         ocr_client=TextLayerOcr(page))
        result["meta"]["ocr"]["provider"] = TEXT_LAYER_PROVIDER
    else:
        if clova is None:
            raise ValueError(f"page {page.number} is a scanned page and needs the OCR settings")
        result = extract(page.image, page.mime_type, clova, settings=settings, client=client, ocr_client=ocr_client)
    result["meta"]["pdf"] = {"page": page.number, "kind": page.kind, "textLayer": page.text_layer}
    return result
