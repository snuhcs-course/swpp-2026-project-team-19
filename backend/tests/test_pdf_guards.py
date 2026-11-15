"""Limits on extracting a whole PDF (I4-P37): what a failed page gives, and that the model calls,
the retries and the time of one PDF are bounded.

Gemini is a scripted fake (each call answers, raises or hangs as the test says), CLOVA a fake
call_ocr, and the clock a list of times, so every run is the same. The PDFs are those of
test_pdf_extraction.
"""

import json
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app import extraction
from app.adapters.extraction import ExtractionError
from app.adapters.hybrid_extraction import HybridMenuExtractor
from app.adapters.pdf_extraction import PdfMenuExtractor
from app.adapters.pdf_guards import FAILURES, PageOutcome, PdfExtraction, PdfGuards, classify, extract_pdf_pages
from app.extraction import clova, gemini, hybrid, pdf

PDFS = Path(__file__).resolve().parent / "fixtures" / "pdf"
SETTINGS = extraction.ExtractionSettings(api_key="secret-test-key", model="gemini-3.5-flash-lite",
                                         thinking_level="medium")
CLOVA = clova.ClovaSettings(invoke_url="https://ocr.example.test/custom/v1/1/abc/general", secret="clova-secret")
OK = json.dumps({"items": [{"raw_name": "글렌피딕 12년", "price_krw": 15000, "pour_ml": 30, "unit": "glass",
                            "source_lines": {"name": ["L006"], "price": ["L007"]}}]})
TIMEOUT = httpx.ReadTimeout("read timed out")
DOWN = httpx.ConnectError("connection refused")


class ServerError(Exception):
    status_code = 400  # not a status the client retries


@pytest.fixture(autouse=True)
def no_waits(monkeypatch):
    monkeypatch.setattr(clova, "sleep", lambda s: None)
    monkeypatch.setattr(gemini, "sleep", lambda s: None)


@pytest.fixture
def model(monkeypatch):
    """A scripted Gemini: `.script` is what each call does, in order (text to answer, an exception
    to raise, or a number of seconds to hang); after the script every call answers OK. `.calls`
    counts the calls and `.settings` keeps the settings each page was called with."""

    class Model:
        def __init__(self):
            self.script, self.calls, self.settings = [], 0, []

        def create(self, **request):
            self.calls += 1
            step = self.script.pop(0) if self.script else OK
            if isinstance(step, Exception):
                raise step
            if isinstance(step, (int, float)):
                time.sleep(step)
                step = OK
            return SimpleNamespace(output_text=step, status="completed", usage=None)

    fake = Model()

    def make_client(settings):
        fake.settings.append(settings)
        return SimpleNamespace(interactions=fake)

    monkeypatch.setattr(gemini, "make_client", make_client)
    return fake


@pytest.fixture
def extractor():
    return PdfMenuExtractor(HybridMenuExtractor(SETTINGS, CLOVA, prompt="v1"))


def text_pages(count: int) -> list[pdf.PdfPage]:
    """`count` text pages (the design menu, renumbered): no OCR call is made for them."""
    [page] = pdf.read_pdf((PDFS / "text_menu_design.pdf").read_bytes())
    return [pdf.PdfPage(**{**page.__dict__, "number": number}) for number in range(1, count + 1)]


class Clock:
    """Returns the given times in order, then the last one."""

    def __init__(self, *times: float):
        self.times = list(times)

    def __call__(self) -> float:
        return self.times.pop(0) if len(self.times) > 1 else self.times[0]


# ---- every page works ----


def test_every_page_is_extracted_with_one_call(extractor, model):
    outcome = extract_pdf_pages(extractor, text_pages(3))

    assert outcome.ok and outcome.stopped is None and model.calls == 3 == outcome.model_attempts
    assert [(p.page, p.failure, p.attempts) for p in outcome.pages] == [(1, None, 1), (2, None, 1), (3, None, 1)]
    assert [p.result.items[0].product_name for p in outcome.pages] == ["글렌피딕 12년"] * 3
    assert outcome.pages[1].raw_output["pdf"]["page"] == 2


def test_a_page_is_called_with_the_guard_limits_not_the_photo_limits(extractor, model):
    extract_pdf_pages(extractor, text_pages(1), PdfGuards(page_attempts=2, attempt_timeout_s=45))

    [settings] = model.settings
    assert (settings.max_attempts, settings.wall_timeout_s, settings.request_timeout_s) == (2, 45, 45)
    assert (settings.model, settings.api_key) == (SETTINGS.model, SETTINGS.api_key)
    assert (SETTINGS.max_attempts, SETTINGS.wall_timeout_s) == (6, 330)  # the extractor's own settings are kept
    assert extractor.hybrid.settings is SETTINGS


# ---- a failed page is an outcome with a code ----


@pytest.mark.parametrize("script, failure, attempts, message", [
    ([TIMEOUT, TIMEOUT, TIMEOUT], "model_timeout", 3, "gave up after 3 attempts; last error ReadTimeout"),
    ([DOWN, DOWN, DOWN], "model_call_failed", 3, "gave up after 3 attempts; last error ConnectError"),
    ([ServerError("bad request")], "model_call_failed", 1, "ServerError: bad request"),
    (["{oops"], "invalid_output", 1, "not valid hybrid v1 output"),
])
def test_a_failed_page_has_a_code_and_the_other_pages_are_still_extracted(extractor, model, script, failure, attempts,
                                                                          message):
    model.script = list(script)

    outcome = extract_pdf_pages(extractor, text_pages(3))

    first, second, third = outcome.pages
    assert (first.failure, first.attempts, first.result) == (failure, attempts, None) and message in first.message
    assert first.raw_output["pdf"] == {"page": 1, "kind": "text", "textLayer": "used"}
    assert second.ok and third.ok and not outcome.ok and outcome.stopped is None
    assert failure in FAILURES


def test_an_attempt_that_hangs_is_cut_and_the_page_fails_as_a_timeout(extractor, model):
    model.script = [5, 5]

    started = time.monotonic()
    outcome = extract_pdf_pages(extractor, text_pages(1), PdfGuards(page_attempts=2, attempt_timeout_s=0.05))

    assert time.monotonic() - started < 2  # two attempts of 0.05 s, not two hangs of 5 s
    [page] = outcome.pages
    assert (page.failure, page.attempts) == ("model_timeout", 2) and "no response within 0.05s" in page.message


def test_a_transient_error_is_retried_and_the_page_succeeds(extractor, model):
    model.script = [TIMEOUT, DOWN]

    outcome = extract_pdf_pages(extractor, text_pages(1))

    assert outcome.ok and outcome.pages[0].attempts == 3 and model.calls == 3


def test_a_page_that_fails_before_the_model_call_is_a_failed_page(extractor, model, monkeypatch):
    def unsupported(*args, **kwargs):
        raise extraction.UnsupportedImageError("not an image")

    monkeypatch.setattr("app.adapters.pdf_extraction.extract_pdf_page", unsupported)

    outcome = extract_pdf_pages(extractor, text_pages(1))

    assert (outcome.pages[0].failure, outcome.pages[0].attempts, model.calls) == ("page_failed", 0, 0)


def test_classify_reads_the_error_chain():
    def chained(*errors):
        for outer, inner in zip(errors, errors[1:]):
            outer.__cause__ = inner
        return errors[0]

    call = extraction.ModelCallError("gave up", attempts=3)
    assert classify(chained(ExtractionError("x"), ExtractionError("y"), call, gemini.HardTimeout("hung"))) == \
        "model_timeout"
    assert classify(chained(ExtractionError("x"), extraction.ModelCallError("no", attempts=1))) == "model_call_failed"
    assert classify(chained(ExtractionError("x"), extraction.InvalidModelOutputError("bad", raw_text="{", meta={}))) \
        == "invalid_output"
    assert classify(ExtractionError("a message that says ModelCallError HardTimeout")) == "page_failed"
    loop = ExtractionError("loop")
    loop.__cause__ = loop
    assert classify(loop) == "page_failed"


# ---- retries are bounded ----


def test_a_page_gets_at_most_page_attempts(extractor, model):
    model.script = [TIMEOUT] * 10

    outcome = extract_pdf_pages(extractor, text_pages(1), PdfGuards(page_attempts=2))

    assert model.calls == 2 and outcome.pages[0].attempts == 2


def test_the_retries_of_all_pages_together_are_bounded(extractor, model):
    model.script = [TIMEOUT] * 100  # the model never answers
    guards = PdfGuards(page_attempts=3, document_retries=3, failed_pages=99)

    outcome = extract_pdf_pages(extractor, text_pages(6), guards)

    # page 1 uses two retries, page 2 the last one, and every later page gets one attempt
    assert [page.attempts for page in outcome.pages] == [3, 2, 1, 1, 1, 1]
    assert [settings.max_attempts for settings in model.settings] == [3, 2, 1, 1, 1, 1]
    assert model.calls == 6 + 3 == outcome.model_attempts
    assert {page.failure for page in outcome.pages} == {"model_timeout"}


def test_retries_a_page_did_not_need_stay_available(extractor, model):
    model.script = [OK, TIMEOUT, OK, OK, TIMEOUT, TIMEOUT, OK]

    outcome = extract_pdf_pages(extractor, text_pages(4), PdfGuards(page_attempts=3, document_retries=3))

    assert outcome.ok and [page.attempts for page in outcome.pages] == [1, 2, 1, 3]
    assert [settings.max_attempts for settings in model.settings] == [3, 3, 3, 3]


@pytest.mark.parametrize("pages", [1, 4, 15])
def test_the_model_is_never_called_more_than_pages_plus_document_retries(extractor, model, pages):
    model.script = [DOWN] * 1000
    guards = PdfGuards(failed_pages=99)

    outcome = extract_pdf_pages(extractor, text_pages(pages), guards)

    assert model.calls <= pages + guards.document_retries and model.calls == outcome.model_attempts
    assert len(outcome.pages) == pages


def test_no_retries_at_all(extractor, model):
    model.script = [TIMEOUT, OK]

    outcome = extract_pdf_pages(extractor, text_pages(2), PdfGuards(document_retries=0))

    assert [(page.failure, page.attempts) for page in outcome.pages] == [("model_timeout", 1), (None, 1)]


# ---- pages are not tried after too many failures or after the deadline ----


def test_after_failed_pages_no_further_page_is_tried(extractor, model):
    model.script = ["{oops", OK, "{oops"]

    outcome = extract_pdf_pages(extractor, text_pages(5), PdfGuards(failed_pages=2))

    assert [page.failure for page in outcome.pages] == ["invalid_output", None, "invalid_output", "not_attempted",
                                                        "not_attempted"]
    assert outcome.stopped == "too_many_failed_pages" and model.calls == 3
    assert outcome.pages[3].message == "not tried: 2 pages of the PDF had failed" and outcome.pages[3].attempts == 0


def test_failures_on_the_last_pages_do_not_mark_the_run_stopped(extractor, model):
    model.script = [OK, "{oops", "{oops"]

    outcome = extract_pdf_pages(extractor, text_pages(3), PdfGuards(failed_pages=2))

    assert outcome.stopped is None and [page.ok for page in outcome.pages] == [True, False, False]


def test_no_page_starts_after_the_document_deadline(extractor, model):
    clock = Clock(0, 10, 400, 901, 2000)  # start, then the time before pages 1, 2, 3, 4

    outcome = extract_pdf_pages(extractor, text_pages(4), PdfGuards(document_deadline_s=900), clock=clock)

    assert [page.failure for page in outcome.pages] == [None, None, "not_attempted", "not_attempted"]
    assert outcome.stopped == "document_deadline" and model.calls == 2
    assert outcome.pages[2].message == "not tried: the PDF's time limit was reached"


def test_a_page_that_starts_near_the_deadline_gets_one_attempt_cut_at_the_deadline(extractor, model):
    model.script = [OK, TIMEOUT]
    clock = Clock(0, 0, 870)  # 30 s are left before page 2

    outcome = extract_pdf_pages(extractor, text_pages(2), PdfGuards(document_deadline_s=900), clock=clock)

    first, second = model.settings
    assert (first.max_attempts, first.wall_timeout_s) == (3, 120)
    assert (second.max_attempts, second.wall_timeout_s, second.request_timeout_s) == (1, 30, 30)
    assert [(page.failure, page.attempts) for page in outcome.pages] == [(None, 1), ("model_timeout", 1)]


def test_the_deadline_grows_with_the_pages_and_a_short_pdf_keeps_its_retries():
    guards = PdfGuards()

    assert guards.deadline_s(15) == 15 * 90 == 1350  # every page as slow as the 95th percentile (83 s) fits
    assert guards.deadline_s(5) == 450
    assert guards.deadline_s(1) == guards.deadline_s(4) == guards.page_seconds == 435  # one page's worst case
    assert PdfGuards(page_budget_s=30).deadline_s(15) == 450
    assert PdfGuards(document_deadline_s=900).deadline_s(15) == PdfGuards(document_deadline_s=900).deadline_s(1) == 900


def test_a_long_pdf_on_a_slow_day_is_not_cut(extractor, model):
    # 15 pages of 83 s each: the 13th page starts 996 s in, past a fixed 900 s
    clock = Clock(0, *[83 * done for done in range(15)])

    outcome = extract_pdf_pages(extractor, text_pages(15), clock=clock)

    assert outcome.ok and outcome.stopped is None and model.calls == 15


def test_a_one_page_pdf_still_retries(extractor, model):
    model.script = [TIMEOUT, DOWN]

    outcome = extract_pdf_pages(extractor, text_pages(1), clock=Clock(0, 0))

    assert outcome.ok and outcome.pages[0].attempts == 3 and model.settings[0].wall_timeout_s == 120


# ---- scanned pages: the OCR call is bounded too ----


def test_the_ocr_call_of_a_scanned_page_has_a_deadline_and_its_failure_is_not_a_failed_page(extractor, model,
                                                                                           monkeypatch):
    seen = []

    def call_ocr(settings, image, mime_type, client=None):
        seen.append(settings)
        raise clova.ClovaOCRError("CLOVA OCR gave up: deadline of 20s reached")

    monkeypatch.setattr(hybrid, "call_ocr", call_ocr)
    model.script = [json.dumps({"items": [{"raw_name": "글렌피딕 12년", "price_krw": 15000, "pour_ml": 30,
                                           "unit": "glass"}]})]
    [page] = pdf.read_pdf((PDFS / "scanned_menu_1.pdf").read_bytes())

    outcome = extract_pdf_pages(extractor, [page], PdfGuards(ocr_deadline_s=20))

    assert seen[0].deadline_s == 20 and (seen[0].invoke_url, seen[0].secret) == (CLOVA.invoke_url, CLOVA.secret)
    assert CLOVA.deadline_s is None  # the extractor's own settings are kept
    assert outcome.ok and outcome.pages[0].raw_output["hybridFallback"]["reason"].startswith("CLOVA OCR gave up")
    assert outcome.pages[0].attempts == 1


# ---- the guards themselves ----


def test_default_guards_and_the_worst_case_of_one_page():
    guards = PdfGuards()

    assert (guards.page_attempts, guards.attempt_timeout_s, guards.ocr_deadline_s) == (3, 120, 60)
    assert (guards.document_retries, guards.page_budget_s, guards.failed_pages) == (6, 90, 3)
    assert guards.document_deadline_s is None
    assert guards.page_seconds == 60 + 3 * 120 + 5 + 10
    assert PdfGuards(page_attempts=1).page_seconds == 60 + 120
    long = PdfGuards(page_attempts=8, attempt_timeout_s=1, ocr_deadline_s=1)
    assert long.page_seconds == 1 + 8 + (5 + 10 + 20 + 40 + 60 + 60 + 60)  # the wait stops growing at 60 s


@pytest.mark.parametrize("field, value, message", [
    ("page_attempts", 0, "page_attempts must be at least 1"),
    ("failed_pages", 0, "failed_pages must be at least 1"),
    ("document_retries", -1, "document_retries must not be negative"),
    ("attempt_timeout_s", 0, "attempt_timeout_s must be positive"),
    ("ocr_deadline_s", -1, "ocr_deadline_s must be positive"),
    ("document_deadline_s", 0, "document_deadline_s must be positive"),
    ("page_budget_s", 0, "page_budget_s must be positive"),
])
def test_guards_refuse_limits_that_bound_nothing(field, value, message):
    with pytest.raises(ValueError, match=message):
        PdfGuards(**{field: value})


def test_an_empty_run_and_the_outcome_helpers():
    empty = extract_pdf_pages(SimpleNamespace(), [])
    assert empty == PdfExtraction(()) and empty.ok and empty.model_attempts == 0
    assert not PageOutcome(1, failure="not_attempted").ok
