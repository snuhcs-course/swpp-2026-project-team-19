"""PDF menus (I4-P13): pages as images, the text layer as OCR lines, and the failure cases.

The PDFs are in tests/fixtures/pdf (made-up menus; make_pdfs.py there says how each was built):
two text PDFs (a Chrome print and a LibreOffice export), two scanned PDFs (pictures only), one
rotated, one encrypted and one cut short. Gemini goes through a fake client and CLOVA through a
fake call_ocr; no test calls a real API.
"""

import io
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from PIL import Image

from app import extraction
from app.adapters.extraction import ExtractionError
from app.adapters.hybrid_extraction import HybridMenuExtractor
from app.adapters.pdf_extraction import PdfMenuExtractor
from app.extraction import clova, gemini, hybrid, pdf, pdf_hybrid
from app.models import LineType

PDFS = Path(__file__).resolve().parent / "fixtures" / "pdf"
SETTINGS = extraction.ExtractionSettings(api_key="secret-test-key", model="gemini-3.5-flash-lite",
                                         thinking_level="medium")
CLOVA = clova.ClovaSettings(invoke_url="https://ocr.example.test/custom/v1/1/abc/general", secret="clova-secret")


def pages(name: str, **kwargs) -> list[pdf.PdfPage]:
    return pdf.read_pdf((PDFS / name).read_bytes(), **kwargs)


def table(page: pdf.PdfPage) -> list[dict]:
    """The page's text layer as the OCR line table the prompt sees."""
    response = pdf.clova_response(page)
    return clova.ocr_lines_table(clova.build_lines(response), clova.image_size(response, (1, 1)))


def row(rows: list[dict], text: str) -> dict:
    [found] = [r for r in rows if r["text"] == text]
    return found


def ink(page: pdf.PdfPage, box: list[int]) -> int:
    """The darkest pixel of the page image inside a 0-1000 box (0 black, 255 white)."""
    image = Image.open(io.BytesIO(page.image)).convert("L")
    x0, y0, x1, y1 = (round(v / 1000 * side) for v, side in zip(box, (page.width, page.height) * 2))
    return image.crop((x0, y0, x1, y1)).getextrema()[0]


# ---- text PDFs: the text layer becomes lines with boxes on the page image ----


def test_a_text_pdf_page_is_an_image_with_its_lines():
    [page] = pages("text_menu_design.pdf")

    assert (page.number, page.kind, page.text_layer) == (1, "text", "used")
    image = Image.open(io.BytesIO(page.image))
    assert image.format == "JPEG" and image.size == (page.width, page.height)
    assert max(image.size) == pdf.RENDER_LONG_SIDE and page.mime_type == "image/jpeg"
    texts = [" ".join(word.text for word in line) for line in page.lines]
    assert texts[0] == "BAR 오크앤몰트"
    assert "글렌피딕 12년 15,000 190,000" in texts and "와일드터키 101 12,000 -" in texts


def test_name_and_prices_of_a_line_are_separate_ocr_lines_in_reading_order():
    [page] = pages("text_menu_design.pdf")
    rows = table(page)

    texts = [r["text"] for r in rows]
    start = texts.index("글렌피딕 12년")
    assert texts[start:start + 3] == ["글렌피딕 12년", "15,000", "190,000"]  # split at the wide gaps
    name, glass, bottle = rows[start:start + 3]
    assert name["box"][2] < glass["box"][0] < glass["box"][2] < bottle["box"][0]  # left to right
    assert abs(name["box"][1] - glass["box"][1]) <= 3  # on one row of the page
    assert [r["id"] for r in rows[:3]] == ["L001", "L002", "L003"]
    assert all(0 <= v <= 1000 for r in rows for v in r["box"])


@pytest.mark.parametrize("name, text", [
    ("text_menu_design.pdf", "발베니 12년 더블우드"),
    ("text_menu_design.pdf", "340,000"),
    ("text_menu_office.pdf", "맥캘란 12 년 셰리 오크"),
])
def test_a_line_box_lands_on_its_text_in_the_page_image(name, text):
    page = pages(name)[0]
    box = row(table(page), text)["box"]

    assert ink(page, box) < 110  # the letters are inside the box
    height = box[3] - box[1]
    above = [box[0], box[1] - height + 2, box[2], box[1] - 2]
    assert ink(page, above) > 200  # and the gap above the row is blank


def test_every_page_of_a_text_pdf_is_read_in_order():
    first, second = pages("text_menu_office.pdf")

    assert [(p.number, p.kind) for p in (first, second)] == [(1, "text"), (2, "text")]
    assert "아드벡 10 년" in [r["text"] for r in table(first)]
    assert {"버팔로 트레이스", "치즈 플레이트"} <= {r["text"] for r in table(second)}
    assert "아드벡 10 년" not in [r["text"] for r in table(second)]


def test_a_space_the_layout_put_between_digits_and_hangul_does_not_change_the_name_key():
    # LibreOffice spaces "10" and "년" apart (another font), and the text layer reads that as a
    # space. The words are kept as the file has them; matching compares names without spaces.
    from app.core.normalize import normalize

    [name] = [r["text"] for r in table(pages("text_menu_office.pdf")[0]) if r["text"].startswith("아드벡")]
    assert name == "아드벡 10 년" and normalize(name) == normalize("아드벡 10년")


# ---- scanned PDFs and text layers that are not used ----


@pytest.mark.parametrize("name, count", [("scanned_menu_1.pdf", 1), ("scanned_menu_2.pdf", 2)])
def test_a_scanned_pdf_gives_page_images_without_lines(name, count):
    result = pages(name)

    assert [p.number for p in result] == list(range(1, count + 1))
    for page in result:
        assert (page.kind, page.text_layer, page.lines) == ("scanned", "none", ())
        image = Image.open(io.BytesIO(page.image))
        assert image.format == "JPEG" and max(image.size) in (pdf.RENDER_LONG_SIDE, pdf.RENDER_LONG_SIDE + 1)
        assert image.convert("L").getextrema()[0] < 110  # the menu is on the page, not a blank render


def test_a_rotated_page_is_read_as_a_picture():
    [page] = pages("rotated_text.pdf")

    assert (page.kind, page.text_layer, page.lines) == ("scanned", "rotated", ())
    assert page.width > page.height  # drawn as the reader sees it


def test_a_cropped_page_is_read_as_a_picture():
    """The page box does not start at 0: the text positions are not measured from the corner of the
    image, and PDFium gives the text of such a page a line per character."""
    [page] = pages("cropped_text.pdf")

    assert (page.kind, page.text_layer, page.lines) == ("scanned", "offset", ())
    image = Image.open(io.BytesIO(page.image))
    assert image.size == (page.width, page.height) and image.convert("L").getextrema()[0] < 110
    [whole] = pages("text_menu_design.pdf")
    assert page.width / page.height < whole.width / whole.height + 0.01  # the cropped area, not the whole page


def test_a_scan_with_a_typed_header_is_read_as_a_picture():
    """One picture covers the page and the text layer has two lines (a header and a page number):
    the menu is in the picture."""
    [page] = pages("scan_with_header.pdf")

    assert (page.kind, page.text_layer, page.lines) == ("scanned", "partial", ())


def test_a_page_with_a_large_picture_and_enough_text_lines_is_a_text_page(monkeypatch):
    # a designed menu on a background picture: the text is the menu
    monkeypatch.setattr(pdf, "MIN_LINES_OVER_PICTURE", 2)
    [page] = pages("scan_with_header.pdf")

    assert (page.kind, page.text_layer) == ("text", "used")
    assert [" ".join(word.text for word in line) for line in page.lines] == [
        "BAR OAK AND MALT - SAMPLE MENU", "- 1 -"]


def test_a_small_picture_does_not_make_a_text_page_a_picture(monkeypatch):
    monkeypatch.setattr(pdf, "PICTURE_PAGE_SHARE", 1.01)  # as if the picture were a logo
    monkeypatch.setattr(pdf, "MIN_TEXT_CHARS", 5)
    [page] = pages("scan_with_header.pdf")

    assert (page.kind, page.text_layer) == ("text", "used")


class FakeTextPage:
    """A text page that gives the listed characters, each 10 pt wide on one row."""

    def __init__(self, *chars: str):
        self.chars = chars

    def count_chars(self) -> int:
        return len(self.chars)

    def get_text_range(self, index: int, count: int) -> str:
        return self.chars[index]

    def get_charbox(self, index: int) -> tuple[float, float, float, float]:
        return (10.0 * index, 100.0, 10.0 * index + 9, 112.0)


def test_one_character_of_the_file_can_be_several_code_points_or_none():
    """A ligature the file maps to "fi", and a character it maps to nothing: PDFium says the text of
    one character need not be one code point."""
    chars = FakeTextPage("O", "f", "fi", "c", "", "e", " ", "\ufffd\ufffd", "A")

    lines, count, unreadable = pdf._text_lines(chars, 2.0, 200.0)

    assert [[word.text for word in line] for line in lines] == [["Offic", "e", "\ufffd\ufffdA"]]
    assert (count, unreadable) == (7, 1)
    office = lines[0][0]
    assert (office.x0, office.x1, office.y0, office.y1) == (0.0, 78.0, 176.0, 200.0)


def test_a_page_without_a_size_is_a_corrupt_pdf():
    class Flat:
        def get_size(self):
            return (0.0, 842.0)

    with pytest.raises(pdf.PdfCorruptError, match="page 3 of the PDF has no size") as error:
        pdf._page(Flat(), 3)
    assert error.value.code == "pdf_corrupt"


def test_a_text_layer_of_unreadable_characters_is_not_used(monkeypatch):
    # what a font with a broken Unicode mapping gives: here every Hangul syllable
    monkeypatch.setattr(pdf, "_unreadable", lambda char: "가" <= char <= "힣")
    [page] = pages("text_menu_design.pdf")

    assert (page.kind, page.text_layer, page.lines) == ("scanned", "unreadable", ())


@pytest.mark.parametrize("char, expected", [
    ("\ufffd", True), ("\ue000", True), ("\x00", True), ("가", False), ("A", False), ("₩", False),
])
def test_unreadable_characters(char, expected):
    assert pdf._unreadable(char) is expected


def test_a_page_with_only_a_few_characters_has_no_text_layer(monkeypatch):
    monkeypatch.setattr(pdf, "MIN_TEXT_CHARS", 10_000)
    [page] = pages("text_menu_design.pdf")

    assert (page.kind, page.text_layer) == ("scanned", "none")


# ---- files that cannot be read ----


def test_an_encrypted_pdf_is_refused():
    with pytest.raises(pdf.PdfEncryptedError, match="password") as error:
        pages("encrypted.pdf")
    assert error.value.code == "pdf_encrypted"


@pytest.mark.parametrize("data", [
    (PDFS / "corrupt.pdf").read_bytes(),      # cut off after 2000 bytes
    b"",
    b"not a pdf at all",
    b"\xff\xd8\xff\xe0" + b"\x00" * 64,        # a JPEG header
    b"%PDF-1.7\n" + b"garbage" * 50,
])
def test_a_file_that_is_not_a_readable_pdf_is_refused(data):
    with pytest.raises(pdf.PdfCorruptError) as error:
        pdf.read_pdf(data)
    assert error.value.code == "pdf_corrupt"


def test_a_pdf_with_too_many_pages_is_refused_before_any_page_is_drawn(monkeypatch):
    monkeypatch.setattr(pdf, "_page", lambda *args: pytest.fail("a page was drawn"))
    with pytest.raises(pdf.PdfTooManyPagesError, match="2 pages; at most 1") as error:
        pages("text_menu_office.pdf", max_pages=1)
    assert error.value.code == "pdf_too_many_pages"
    assert pdf.MAX_PDF_PAGES == 15  # the photo limit of one import


def test_every_pdf_error_is_a_pdf_error_with_its_own_code():
    errors = [pdf.PdfEncryptedError, pdf.PdfCorruptError, pdf.PdfEmptyError, pdf.PdfTooManyPagesError]
    assert all(issubclass(error, pdf.PdfError) for error in errors)
    assert len({error.code for error in errors}) == 4


# ---- extraction of a page ----


class FakeInteractions:
    def __init__(self, text: str, status: str = "completed"):
        self.text, self.status, self.requests = text, status, []

    def create(self, **request):
        self.requests.append(request)
        usage = SimpleNamespace(total_input_tokens=5000, total_output_tokens=300, total_thought_tokens=700,
                                total_tokens=6000)
        return SimpleNamespace(output_text=self.text, status=self.status, usage=usage)


def answer(page: pdf.PdfPage, category: bool = False) -> dict:
    """What the model would answer for the design menu: one line with a glass and a bottle price."""
    rows = table(page)
    name, glass, bottle = (row(rows, text)["id"] for text in ("글렌피딕 12년", "15,000", "190,000"))
    extra = {"category": "whisky"} if category else {}
    return {"items": [
        {"raw_name": "글렌피딕 12년", "price_krw": 15000, "pour_ml": 30, "unit": "glass",
         "source_lines": {"name": [name], "price": [glass]}, **extra},
        {"raw_name": "글렌피딕 12년", "price_krw": 190000, "pour_ml": None, "unit": "bottle",
         "source_lines": {"name": [name], "price": [bottle]}, **extra},
    ]}


@pytest.fixture
def design_page():
    [page] = pages("text_menu_design.pdf")
    return page


@pytest.fixture
def fake_gemini(monkeypatch, design_page):
    fake = SimpleNamespace(interactions=FakeInteractions(json.dumps(answer(design_page))))
    monkeypatch.setattr(gemini, "make_client", lambda settings: fake)
    return fake.interactions


@pytest.fixture
def no_network(monkeypatch):
    """Any HTTP client the OCR step opens by itself fails the test."""
    monkeypatch.setattr(httpx, "Client", lambda *args, **kwargs: pytest.fail("an HTTP client was opened"))


@pytest.fixture
def fake_ocr(monkeypatch):
    """Replace the CLOVA call of a scanned page; set `.error` to make it fail and read `.calls`."""

    class Fake:
        error = None

        def __init__(self):
            self.calls = []

        def __call__(self, settings, image, mime_type, client=None):
            self.calls.append((settings, mime_type))
            if self.error is not None:
                raise self.error
            [page] = pages("text_menu_design.pdf")
            return {"response": pdf.clova_response(page), "sentSize": [page.width, page.height], "latencyMs": 900,
                    "attempts": 1}

    fake = Fake()
    monkeypatch.setattr(hybrid, "call_ocr", fake)
    return fake


def test_a_text_page_is_extracted_from_its_text_layer_without_an_ocr_call(design_page, fake_gemini, no_network):
    result = pdf_hybrid.extract_pdf_page(design_page, None, settings=SETTINGS)

    [request] = fake_gemini.requests
    text = request["input"][0]["text"]
    assert text.startswith(hybrid.USER_HEADER) and " 글렌피딕 12년\n" in text and " 190,000\n" in text
    assert request["input"][1]["type"] == "image" and request["system_instruction"] == hybrid.load_prompt()
    # the glass and bottle rows of the line are one item with two options, as for a photo
    [item] = result["items"]
    assert item["rawText"] == "글렌피딕 12년"
    assert [(o["priceKrw"], o["pourMl"]) for o in item["options"]] == [(15000, 30), (190000, None)]
    meta = result["meta"]
    assert meta["pdf"] == {"page": 1, "kind": "text", "textLayer": "used"}
    assert meta["ocr"]["provider"] == "pdf-text-layer" and meta["ocr"]["attempts"] == 1
    assert meta["ocr"]["lines"] == table(design_page)
    # the item's box covers its name and both prices, for the review screen's crop
    [source] = meta["itemSources"]
    name, bottle = row(table(design_page), "글렌피딕 12년")["box"], row(table(design_page), "190,000")["box"]
    assert source["box"][0] == name[0] and source["box"][2] == bottle[2]
    assert ink(design_page, source["box"]) < 110


def test_a_text_page_goes_through_prompt_v2_too(design_page, monkeypatch, no_network):
    fake = SimpleNamespace(interactions=FakeInteractions(json.dumps(answer(design_page, category=True))))
    monkeypatch.setattr(gemini, "make_client", lambda settings: fake)

    result = pdf_hybrid.extract_pdf_page(design_page, None, settings=SETTINGS, prompt="v2")

    assert [i["rawText"] for i in result["items"]] == ["글렌피딕 12년"]
    assert result["meta"]["promptVersion"] == "hybrid-v2" and result["meta"]["ocr"]["provider"] == "pdf-text-layer"
    assert result["meta"]["pdf"]["kind"] == "text"


def test_a_scanned_page_is_extracted_with_one_ocr_call(fake_ocr, fake_gemini):
    [page] = pages("scanned_menu_1.pdf")

    result = pdf_hybrid.extract_pdf_page(page, CLOVA, settings=SETTINGS)

    assert fake_ocr.calls == [(CLOVA, "image/jpeg")]
    assert result["meta"]["pdf"] == {"page": 1, "kind": "scanned", "textLayer": "none"}
    assert result["meta"]["ocr"]["provider"] == "clova-general-v2"
    assert [i["rawText"] for i in result["items"]] == ["글렌피딕 12년"]


def test_a_scanned_page_needs_the_ocr_settings_and_a_scanned_page_has_no_text_layer_client():
    [page] = pages("scanned_menu_1.pdf")
    with pytest.raises(ValueError, match="scanned page and needs the OCR settings"):
        pdf_hybrid.extract_pdf_page(page, None, settings=SETTINGS)
    with pytest.raises(ValueError, match="no usable text layer"):
        pdf_hybrid.TextLayerOcr(page)


# ---- the adapter ----


@pytest.fixture
def extractor():
    return PdfMenuExtractor(HybridMenuExtractor(SETTINGS, CLOVA, prompt="v1"))


def test_the_adapter_reads_pages_and_records_what_produced_a_result(extractor):
    assert [p.kind for p in extractor.pages((PDFS / "text_menu_office.pdf").read_bytes())] == ["text", "text"]
    with pytest.raises(pdf.PdfTooManyPagesError):
        extractor.pages((PDFS / "text_menu_office.pdf").read_bytes(), max_pages=1)
    assert extractor.pipeline_version == "bottlemap-menu-hybrid-prompthybrid-v1-thinking-medium-pdf"
    assert (extractor.approach, extractor.provider, extractor.model_name) == (
        extractor.hybrid.approach, extractor.hybrid.provider, "gemini-3.5-flash-lite")


def test_the_adapter_extracts_a_text_page(extractor, design_page, fake_gemini, no_network):
    result = extractor.extract_page(design_page)

    [item] = result.items
    assert (item.line_type, item.product_name) == (LineType.PRODUCT, "글렌피딕 12년")
    assert [o.price_krw for o in item.options] == [15000, 190000]
    assert result.raw_output["pdf"] == {"page": 1, "kind": "text", "textLayer": "used"}
    assert result.raw_output["ocr"]["provider"] == "pdf-text-layer"
    assert result.raw_output["itemSources"][0]["box"] is not None


def test_the_adapter_sends_a_scanned_page_through_the_hybrid_extractor(extractor, fake_ocr, fake_gemini):
    [page] = pages("scanned_menu_1.pdf")

    result = extractor.extract_page(page)

    assert len(fake_ocr.calls) == 1 and result.items[0].product_name == "글렌피딕 12년"
    assert result.raw_output["pdf"] == {"page": 1, "kind": "scanned", "textLayer": "none"}
    assert result.raw_output["mode"] == "hybrid"


def test_a_scanned_page_falls_back_to_gemini_only_when_ocr_fails(extractor, fake_ocr, monkeypatch, caplog):
    [page] = pages("scanned_menu_1.pdf")
    fake_ocr.error = clova.ClovaOCRError("CLOVA OCR failed after 3 attempt(s): HTTP 500")
    fallback = SimpleNamespace(interactions=FakeInteractions(json.dumps({"items": [
        {"raw_name": "글렌피딕 12년", "price_krw": 15000, "pour_ml": 30, "unit": "glass"}]})))
    monkeypatch.setattr(gemini, "make_client", lambda settings: fallback)

    with caplog.at_level(logging.WARNING):
        result = extractor.extract_page(page)

    assert result.items[0].product_name == "글렌피딕 12년"
    assert result.raw_output["hybridFallback"] == {"reason": "CLOVA OCR failed after 3 attempt(s): HTTP 500"}
    assert result.raw_output["pdf"]["kind"] == "scanned"
    assert "falling back to Gemini only" in caplog.text


@pytest.mark.parametrize("text, status, message", [
    ("{oops", "completed", "not valid hybrid v1 output"),
    ("{}", "failed", "interaction status is 'failed'"),
])
def test_a_text_page_the_model_fails_on_fails_with_its_pdf_meta(extractor, design_page, monkeypatch, no_network,
                                                                 text, status, message):
    fake = SimpleNamespace(interactions=FakeInteractions(text, status))
    monkeypatch.setattr(gemini, "make_client", lambda settings: fake)

    with pytest.raises(ExtractionError, match=message) as error:
        extractor.extract_page(design_page)

    raw = error.value.raw_output
    assert raw["pdf"] == {"page": 1, "kind": "text", "textLayer": "used"}
    assert raw["ocr"]["provider"] == "pdf-text-layer" and raw["rawText"] == text


def test_a_scanned_page_the_model_fails_on_keeps_its_pdf_meta(extractor, fake_ocr, monkeypatch):
    [page] = pages("scanned_menu_1.pdf")
    fake = SimpleNamespace(interactions=FakeInteractions("{oops"))
    monkeypatch.setattr(gemini, "make_client", lambda settings: fake)

    with pytest.raises(ExtractionError, match="not valid hybrid v1 output") as error:
        extractor.extract_page(page)

    assert error.value.raw_output["pdf"] == {"page": 1, "kind": "scanned", "textLayer": "none"}


def test_a_gemini_call_that_keeps_failing_fails_a_text_page(extractor, design_page, monkeypatch, no_network):
    def boom(settings, request, client=None):
        raise extraction.ModelCallError("Gemini call failed after 3 attempts", attempts=3)

    monkeypatch.setattr(hybrid, "call_with_retries", boom)

    with pytest.raises(ExtractionError, match="ModelCallError") as error:
        extractor.extract_page(design_page)

    assert error.value.raw_output == {"attempts": 3, "pdf": {"page": 1, "kind": "text", "textLayer": "used"}}


def test_other_extraction_errors_and_rejected_items_fail_a_text_page(extractor, design_page, monkeypatch):
    def unsupported(*args, **kwargs):
        raise extraction.UnsupportedImageError("not an image")

    monkeypatch.setattr("app.adapters.pdf_extraction.extract_pdf_page", unsupported)
    with pytest.raises(ExtractionError, match="UnsupportedImageError: not an image") as error:
        extractor.extract_page(design_page)
    assert error.value.raw_output == {"pdf": {"page": 1, "kind": "text", "textLayer": "used"}}

    bad = {"items": [{"itemOrder": 1, "rawText": "x", "lineType": "drink", "options": []}], "meta": {"mode": "hybrid"}}
    monkeypatch.setattr("app.adapters.pdf_extraction.extract_pdf_page", lambda *args, **kwargs: bad)
    with pytest.raises(ExtractionError, match="lineType") as error:
        extractor.extract_page(design_page)
    assert error.value.raw_output == {"mode": "hybrid"}


def test_a_pdf_without_pages_and_a_page_that_cannot_be_drawn_are_refused(monkeypatch):
    import pypdfium2

    class Empty:
        def __len__(self):
            return 0

        def close(self):
            pass

    monkeypatch.setattr(pdf, "_open", lambda data: Empty())
    with pytest.raises(pdf.PdfEmptyError, match="no page") as error:
        pdf.read_pdf(b"%PDF")
    assert error.value.code == "pdf_empty"

    monkeypatch.undo()

    def broken(page, number):
        raise pypdfium2.PdfiumError("Failed to load page.")

    monkeypatch.setattr(pdf, "_page", broken)
    with pytest.raises(pdf.PdfCorruptError, match="page 1 of the PDF cannot be read"):
        pages("text_menu_design.pdf")


# ---- the check at upload: the same refusals as read_pdf, without drawing a page ----


@pytest.mark.parametrize("name, count", [
    ("text_menu_design.pdf", 1), ("text_menu_office.pdf", 2), ("scanned_menu_2.pdf", 2), ("rotated_text.pdf", 1),
])
def test_check_pdf_counts_the_pages_without_drawing_them(monkeypatch, name, count):
    monkeypatch.setattr(pdf, "_page", lambda *args: pytest.fail("a page was drawn"))

    assert pdf.check_pdf((PDFS / name).read_bytes()) == count


@pytest.mark.parametrize("data, kwargs, error", [
    ((PDFS / "encrypted.pdf").read_bytes(), {}, pdf.PdfEncryptedError),
    ((PDFS / "corrupt.pdf").read_bytes(), {}, pdf.PdfCorruptError),
    (b"", {}, pdf.PdfCorruptError),
    (b"\xff\xd8\xff\xe0" + b"\x00" * 64, {}, pdf.PdfCorruptError),
    ((PDFS / "text_menu_office.pdf").read_bytes(), {"max_pages": 1}, pdf.PdfTooManyPagesError),
])
def test_check_pdf_and_read_pdf_refuse_the_same_files_with_the_same_message(data, kwargs, error):
    with pytest.raises(error) as checked:
        pdf.check_pdf(data, **kwargs)
    with pytest.raises(error) as read:
        pdf.read_pdf(data, **kwargs)
    assert str(checked.value) == str(read.value) and checked.value.code == read.value.code


def test_check_pdf_refuses_a_pdf_without_pages(monkeypatch):
    class Empty:
        closed = False

        def __len__(self):
            return 0

        def close(self):
            self.closed = True

    empty = Empty()
    monkeypatch.setattr(pdf, "_open", lambda data: empty)
    with pytest.raises(pdf.PdfEmptyError):
        pdf.check_pdf(b"%PDF")
    assert empty.closed


def test_a_file_that_passes_the_check_is_read_page_by_page():
    data = (PDFS / "scanned_menu_2.pdf").read_bytes()
    assert pdf.check_pdf(data) == len(pdf.read_pdf(data))
