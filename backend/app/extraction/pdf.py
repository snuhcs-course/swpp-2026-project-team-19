"""PDF menus (I4-P13): each page as an image, and the text layer of a page as OCR-like lines.

    pages = read_pdf(data)             # raises PdfError: encrypted, corrupt, empty, too many pages
    pages[0].image, pages[0].kind      # JPEG bytes of the page; "text" or "scanned"
    pages[0].lines                     # words with pixel boxes on that image ("text" pages only)

The rest of the pipeline works on one image per menu photo: the review screen crops a menu line
out of the image by its box. So a PDF becomes one image per page, and everything after extraction
stays as it is.

Two kinds of page:

- "text": the PDF has the menu as text (exported from a word processor or a design tool). The
  words and their positions are read from the file, so no OCR call is needed and no character is
  misread. `clova_response` puts them in the shape of a CLOVA OCR answer, which is what the hybrid
  extraction reads (app.extraction.pdf_hybrid).
- "scanned": the page is a picture (a scan or a photo saved as PDF), or its text cannot be
  trusted. The page image goes through OCR like a photo. `text_layer` says why the text was not
  used: "none" (fewer than MIN_TEXT_CHARS characters), "unreadable" (too many characters without
  a Unicode value, which a font with a broken mapping gives) or "rotated" (the page has a
  rotation, and its text positions are not mapped onto the rotated image here).

The words are kept as the file has them. A layout that sets digits and Hangul in different fonts
can leave a gap the text layer reads as a space ("10 년"); matching compares names without spaces
(app.core.normalize), so the product found is the same.

Not handled: a scan that carries hidden text from the scanner's own OCR is read as a "text" page,
with whatever quality that OCR had.
"""

import io
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

import pypdfium2 as pdfium

# The same limit as menu photos in one import (app.services.menu_import_upload.MAX_IMAGES).
MAX_PDF_PAGES = 15
# Long side of the page image in pixels. An A4 page comes out at about 240 dpi.
RENDER_LONG_SIDE = 2000
JPEG_QUALITY = 90
PAGE_MIME_TYPE = "image/jpeg"
# A page with fewer characters than this has no text layer worth reading (a page number, a stamp).
MIN_TEXT_CHARS = 10
# Above this share of characters without a usable Unicode value, the text layer is not trusted.
MAX_UNREADABLE_SHARE = 0.05


class PdfError(Exception):
    """The file cannot be used as a menu PDF. `code` says why, for the caller's own message."""

    code = "pdf_error"


class PdfEncryptedError(PdfError):
    """The file needs a password to open."""

    code = "pdf_encrypted"


class PdfCorruptError(PdfError):
    """The bytes are not a PDF that can be opened, or a page of it cannot be drawn."""

    code = "pdf_corrupt"


class PdfEmptyError(PdfError):
    """The file opens but has no page."""

    code = "pdf_empty"


class PdfTooManyPagesError(PdfError):
    """The file has more pages than one import takes."""

    code = "pdf_too_many_pages"


@dataclass(frozen=True)
class PdfWord:
    """A run of characters without a space, with its box in pixels of the page image."""

    text: str
    x0: float
    y0: float
    x1: float
    y1: float


@dataclass(frozen=True)
class PdfPage:
    number: int  # 1-based
    image: bytes
    width: int
    height: int
    kind: Literal["text", "scanned"]
    # Why the text layer was not used; "used" on a text page.
    text_layer: Literal["used", "none", "unreadable", "rotated"]
    # Text lines top to bottom as the file orders them; empty on a scanned page.
    lines: tuple[tuple[PdfWord, ...], ...] = ()
    mime_type: str = PAGE_MIME_TYPE


def _open(data: bytes) -> pdfium.PdfDocument:
    if not data:
        raise PdfCorruptError("the file is empty")
    try:
        return pdfium.PdfDocument(data)
    except pdfium.PdfiumError as error:
        if "password" in str(error).lower():
            raise PdfEncryptedError("the PDF is protected with a password") from error
        raise PdfCorruptError(f"the file cannot be opened as a PDF: {error}") from error


def _unreadable(char: str) -> bool:
    """A character the text layer gives without a usable Unicode value."""
    return char in ("\ufffd", "\x00") or unicodedata.category(char) in ("Co", "Cn", "Cs")


def _text_lines(textpage: pdfium.PdfTextPage, scale: float, page_height: float) -> tuple[list[list[PdfWord]], int, int]:
    """(lines of words, characters read, unreadable characters). Boxes are in image pixels."""
    lines: list[list[PdfWord]] = [[]]
    word: list[tuple[str, tuple[float, float, float, float]]] = []
    count = unreadable = 0

    def end_word() -> None:
        if word:
            boxes = [box for _, box in word]
            lines[-1].append(PdfWord(
                text="".join(char for char, _ in word),
                x0=min(b[0] for b in boxes) * scale,
                y0=(page_height - max(b[3] for b in boxes)) * scale,
                x1=max(b[2] for b in boxes) * scale,
                y1=(page_height - min(b[1] for b in boxes)) * scale,
            ))
            word.clear()

    for index in range(textpage.count_chars()):
        char = textpage.get_text_range(index, 1)
        if char in ("\r", "\n"):
            end_word()
            if lines[-1]:
                lines.append([])
            continue
        if not char or char.isspace():
            end_word()
            continue
        count += 1
        if _unreadable(char):
            unreadable += 1
        word.append((char, textpage.get_charbox(index)))
    end_word()
    return [line for line in lines if line], count, unreadable


def _page(page: pdfium.PdfPage, number: int) -> PdfPage:
    width_pt, height_pt = page.get_size()
    scale = RENDER_LONG_SIDE / max(width_pt, height_pt)
    image = page.render(scale=scale).to_pil().convert("RGB")
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=JPEG_QUALITY)

    textpage = page.get_textpage()
    try:
        lines, count, unreadable = _text_lines(textpage, scale, height_pt)
    finally:
        textpage.close()
    if count < MIN_TEXT_CHARS:
        text_layer = "none"
    elif unreadable / count > MAX_UNREADABLE_SHARE:
        text_layer = "unreadable"
    elif page.get_rotation():
        text_layer = "rotated"
    else:
        text_layer = "used"
    used = text_layer == "used"
    return PdfPage(
        number=number,
        image=out.getvalue(),
        width=image.width,
        height=image.height,
        kind="text" if used else "scanned",
        text_layer=text_layer,
        lines=tuple(tuple(line) for line in lines) if used else (),
    )


def _page_count(document: pdfium.PdfDocument, max_pages: int) -> int:
    count = len(document)
    if count == 0:
        raise PdfEmptyError("the PDF has no page")
    if count > max_pages:
        raise PdfTooManyPagesError(f"the PDF has {count} pages; at most {max_pages} can be read")
    return count


def check_pdf(data: bytes, *, max_pages: int = MAX_PDF_PAGES) -> int:
    """The number of pages of a menu PDF, without drawing any page: the check to run when the file
    is uploaded. Raises the same PdfError as read_pdf when the file is encrypted, corrupt, empty
    or longer than `max_pages`. A file that passes can still have a page that cannot be drawn;
    read_pdf raises PdfCorruptError for that one."""
    document = _open(data)
    try:
        return _page_count(document, max_pages)
    finally:
        document.close()


def read_pdf(data: bytes, *, max_pages: int = MAX_PDF_PAGES) -> list[PdfPage]:
    """The pages of a menu PDF, in order. Raises PdfError before any page is drawn when the file
    is encrypted, corrupt, empty or longer than `max_pages` (the checks of check_pdf)."""
    document = _open(data)
    try:
        count = _page_count(document, max_pages)
        pages = []
        for index in range(count):
            try:
                page = document[index]
                try:
                    pages.append(_page(page, index + 1))
                finally:
                    page.close()
            except pdfium.PdfiumError as error:
                raise PdfCorruptError(f"page {index + 1} of the PDF cannot be read: {error}") from error
        return pages
    finally:
        document.close()


def clova_response(page: PdfPage) -> dict[str, Any]:
    """The text layer of a "text" page in the shape of a CLOVA General OCR answer.

    One field per word with its four corners in pixels of the page image, `lineBreak` on the last
    word of a line, and `convertedImageInfo` giving the pixel size the corners refer to, so
    app.extraction.clova.build_lines and ocr_lines_table read it like a real answer.
    """
    fields = []
    for line in page.lines:
        for position, word in enumerate(line):
            fields.append({
                "inferText": word.text,
                "boundingPoly": {"vertices": [
                    {"x": word.x0, "y": word.y0}, {"x": word.x1, "y": word.y0},
                    {"x": word.x1, "y": word.y1}, {"x": word.x0, "y": word.y1},
                ]},
                "lineBreak": position == len(line) - 1,
            })
    return {"images": [{
        "inferResult": "SUCCESS",
        "convertedImageInfo": {"width": page.width, "height": page.height},
        "fields": fields,
    }]}
