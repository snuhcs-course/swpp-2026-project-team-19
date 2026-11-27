"""PDF pages through the route ladder of MENU_EXTRACTOR=openrouter (I5-P19 follow-up G): the routes,
the PDF limits of I4-P37 on top of them, and pages counted like photos. OpenRouter is a fake HTTP
client, Gemini a fake SDK client, CLOVA a fake call; no test calls a real API. The PDFs are those
of test_pdf_extraction."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app import extraction
from app.adapters.extraction import ExtractionError, MockMenuExtractor
from app.adapters.gemini_extraction import GeminiMenuExtractor
from app.adapters.hybrid_extraction import HybridMenuExtractor
from app.adapters.openrouter_extraction import OpenRouterMenuExtractor
from app.adapters.pdf_extraction import PdfMenuExtractor
from app.adapters.pdf_guards import PdfGuards, _attempts, extract_pdf_pages
from app.adapters.pdf_routed_extraction import RoutedPdfMenuExtractor, pdf_extractor_for
from app.core.errors import ApiError
from app.extraction import gemini, hybrid, openrouter, pdf
from app.extraction.clova import ClovaOCRError
from app.extraction.routed import CircuitBreaker
from app.services.paid_photo_budget import DailyPaidBudget
from app.services.request_limits import MENU_IMPORT_PHOTOS, InMemoryDailyLimiter, acquire_menu_photos
from tests.test_hybrid_extraction_adapter import CLOVA, OCR_RESPONSE, SETTINGS
from tests.test_openrouter_extraction import (
    DIRECT,
    FALLBACK,
    PRIMARY,
    ROUTE,
    ApiError as GeminiApiError,
    FakeHttp,
    failed,
    gemini_fake,
    ok,
)

PDFS = Path(__file__).resolve().parent / "fixtures" / "pdf"
NOON = datetime(2026, 11, 26, 3, tzinfo=UTC)


def pages(name):
    return pdf.read_pdf((PDFS / name).read_bytes())


@pytest.fixture(autouse=True)
def no_waits(monkeypatch):
    monkeypatch.setattr(openrouter, "sleep", lambda seconds: None)
    monkeypatch.setattr(gemini, "sleep", lambda seconds: None)


@pytest.fixture
def clova_calls(monkeypatch):
    """Counts the CLOVA calls of scanned pages; a text page must never get here with the CLOVA settings."""
    real = hybrid.call_ocr

    class Calls(list):
        error = None  # set to make the CLOVA call of a scanned page fail

    calls = Calls()

    def call_ocr(settings, image, mime_type, client=None):
        if settings.invoke_url.startswith("pdf-text-layer://"):
            return real(settings, image, mime_type, client)  # answered by the page's text layer, no request
        calls.append(settings)
        if calls.error is not None:
            raise calls.error
        return {"response": OCR_RESPONSE, "sentSize": [1000, 2000], "latencyMs": 900, "attempts": 1}

    monkeypatch.setattr(hybrid, "call_ocr", call_ocr)
    return calls


@pytest.fixture
def make(monkeypatch, clova_calls):
    """extractor, http, gemini = make(http answers...): a routed PDF extractor on fakes."""

    def build(*answers, gem=None, breaker=None, budget=None, route=ROUTE):
        http, gem = FakeHttp(*(answers or (ok(),))), gem or gemini_fake()
        monkeypatch.setattr(openrouter.httpx, "post", http.post)
        monkeypatch.setattr(gemini, "make_client", lambda settings: gem)
        return RoutedPdfMenuExtractor(OpenRouterMenuExtractor(route, CLOVA, breaker, budget)), http, gem

    return build


# ---- one page through the routes ----


def test_a_text_page_is_read_at_stage_0_without_a_clova_call(make, clova_calls):
    extractor, http, gem = make()
    [page] = pages("text_menu_design.pdf")

    result = extractor.extract_page(page)

    raw = result.raw_output
    assert clova_calls == [] and len(http.posts) == 1 and gem.requests == []
    assert raw["route"] == {"stage": 0, "path": "openrouter", "model": PRIMARY, "provider": "Google", "skipped": []}
    assert raw["pdf"] == {"page": 1, "kind": "text", "textLayer": "used"}
    assert raw["ocr"]["provider"] == "pdf-text-layer" and raw["ocr"]["lines"]
    # the same record as a photo: model, tokens, cost, latency
    assert (raw["model"], raw["inputTokens"], raw["outputTokens"], raw["thoughtTokens"], raw["costUsd"]) == (
        PRIMARY, 8000, 9000, 4000, 0.03)
    assert "latencyMs" in raw and raw["promptVersion"] == "hybrid-v2.1"
    # the page's own text is what the model was sent as OCR lines
    assert "발베니 12년 더블우드" in http.posts[0]["json"]["messages"][1]["content"][0]["text"]
    assert [item.item_order for item in result.items] == [1, 2, 3, 4]


@pytest.mark.parametrize("answers, gem, stage, model, skipped", [
    ((ok(model=FALLBACK, provider="Anthropic"),), None, 1, FALLBACK, []),
    ((failed(402),), None, 2, DIRECT, [0]),
    ((failed(503),), "direct_429", 3, "gemini-3.5-flash-lite", [0, 2]),
])
def test_a_text_page_takes_stages_1_to_3_like_a_photo(make, answers, gem, stage, model, skipped):
    gem = gemini_fake(direct=GeminiApiError(429)) if gem else None
    extractor, _, _ = make(*answers, gem=gem)

    raw = extractor.extract_page(pages("text_menu_design.pdf")[0]).raw_output

    assert (raw["route"]["stage"], raw["route"]["model"], raw["model"]) == (stage, model, model)
    assert [skip["stage"] for skip in raw["route"]["skipped"]] == skipped
    assert raw["pdf"]["kind"] == "text" and raw["ocr"]["provider"] == "pdf-text-layer"


def test_stage_4_fails_the_page_with_the_route_and_the_page_in_the_record(make):
    extractor, _, _ = make(failed(402), gem=gemini_fake(direct=GeminiApiError(429), lite=GeminiApiError(503)))

    with pytest.raises(ExtractionError, match="AllRoutesFailedError") as caught:
        extractor.extract_page(pages("text_menu_design.pdf")[0])

    raw = caught.value.raw_output
    assert raw["route"]["stage"] == 4 and [skip["stage"] for skip in raw["route"]["skipped"]] == [0, 2, 3]
    assert raw["pdf"] == {"page": 1, "kind": "text", "textLayer": "used"} and raw["attempts"] == 1 + 2 + 2


def test_an_invalid_answer_fails_the_page_with_its_text_and_the_page(make):
    extractor, _, gem = make(ok(text="{}"))

    with pytest.raises(ExtractionError, match="InvalidModelOutputError") as caught:
        extractor.extract_page(pages("text_menu_design.pdf")[0])

    raw = caught.value.raw_output
    assert raw["rawText"] == "{}" and raw["route"]["stage"] == 0 and raw["pdf"]["page"] == 1
    assert raw["ocr"]["provider"] == "pdf-text-layer" and gem.requests == []


def test_a_scanned_page_gets_one_clova_call_and_then_the_routes(make, clova_calls):
    extractor, http, _ = make()
    first, second = pages("scanned_menu_2.pdf")

    raws = [extractor.extract_page(page).raw_output for page in (first, second)]

    assert len(clova_calls) == 2 and len(http.posts) == 2  # one OCR call and one model call a page
    assert [raw["pdf"] for raw in raws] == [{"page": 1, "kind": "scanned", "textLayer": "none"},
                                           {"page": 2, "kind": "scanned", "textLayer": "none"}]
    assert all(raw["ocr"]["provider"] == "clova-general-v2" and raw["route"]["stage"] == 0 for raw in raws)


def test_a_scanned_page_whose_ocr_fails_goes_through_the_gemini_only_extractor(make, clova_calls, monkeypatch):
    extractor, http, _ = make()
    clova_calls.error = ClovaOCRError("CLOVA is down")
    monkeypatch.setattr(extraction, "extract_menu",
                        lambda image, mime_type, *, settings=None, client=None: {"items": [], "meta": {"model": settings.model}})

    raw = extractor.extract_page(pages("scanned_menu_1.pdf")[0]).raw_output

    assert http.posts == [] and raw["hybridFallback"] == {"reason": "CLOVA is down"}
    assert raw["pdf"] == {"page": 1, "kind": "scanned", "textLayer": "none"} and "ocr" not in raw


def test_the_extractor_is_recorded_like_the_photo_extractor_with_pdf_added(make):
    extractor, _, _ = make()

    assert (extractor.provider, extractor.model_name) == ("naver-clova+openrouter", PRIMARY)
    assert extractor.pipeline_version == "bottlemap-menu-hybrid-prompthybrid-v2.1-reasoning-medium-pdf"
    assert len(extractor.pages((PDFS / "text_menu_office.pdf").read_bytes())) == 2


# ---- pages count like photos ----


def test_pages_use_the_photo_extractors_daily_paid_budget(make):
    budget = DailyPaidBudget(1, lambda since: 0, lambda: NOON)
    extractor, http, gem = make(budget=budget)
    first, second = pages("text_menu_office.pdf")

    stages = [extractor.extract_page(page).raw_output["route"] for page in (first, second)]

    assert [route["stage"] for route in stages] == [0, 2] and budget.used() == 1
    assert stages[1]["skipped"] == [{"stage": 0, "reason": "daily_paid_limit", "limit": 1}]
    assert len(http.posts) == 1 and len(gem.requests) == 1


def test_a_pdf_counts_its_pages_against_the_users_daily_photo_limit():
    limiter, document = InMemoryDailyLimiter(daily_limit=3), pages("text_menu_office.pdf")

    acquire_menu_photos(limiter, "owner", len(document), NOON)  # what the upload calls for a PDF

    assert limiter.used("owner", MENU_IMPORT_PHOTOS, NOON) == 2
    with pytest.raises(ApiError) as refused:  # 1 left, 2 pages: the whole PDF is refused
        acquire_menu_photos(limiter, "owner", len(document), NOON)
    assert refused.value.details == {"retryAfter": "2026-11-26T15:00:00Z", "dailyLimit": 3, "remaining": 1, "requested": 2}
    assert limiter.used("owner", MENU_IMPORT_PHOTOS, NOON) == 2


# ---- the PDF limits of I4-P37 on the routes ----


def test_a_page_under_the_guards_gets_its_limits_on_every_route_and_keeps_the_shared_state(make):
    breaker, budget = CircuitBreaker(3, 600), DailyPaidBudget(5, lambda since: 0, lambda: NOON)
    extractor, _, _ = make(breaker=breaker, budget=budget)

    limited = extractor.for_page(2, 120.0, 60.0)

    route = limited.openrouter.route
    assert (route.openrouter.max_attempts, route.openrouter.request_timeout_s, route.openrouter.wall_timeout_s) == (2, 120, 120)
    assert (route.direct.max_attempts, route.direct.wall_timeout_s, route.lite.max_attempts, route.lite.wall_timeout_s) == (
        1, 120, 1, 120)
    assert (limited.openrouter.clova.deadline_s, limited.openrouter.clova.timeout_s) == (30, 30)
    assert limited.openrouter.breaker is breaker and limited.openrouter.budget is budget
    assert (route.openrouter.model, route.prompt, route.direct.model) == (PRIMARY, "v2.1", DIRECT)
    assert extractor.openrouter.route.openrouter.max_attempts == 3  # the photo extractor is not changed


def test_a_page_keeps_stage_2_off_when_it_is_off_for_photos(make):
    extractor, _, gem = make(failed(402), route=replace(ROUTE, direct=None))

    limited = extractor.for_page(2, 120.0, 60.0)
    raw = limited.extract_page(pages("text_menu_design.pdf")[0]).raw_output

    assert limited.openrouter.route.direct is None and limited.openrouter.route.lite.max_attempts == 1
    assert raw["route"]["stage"] == 3
    assert raw["route"]["skipped"][1:] == [{"stage": 2, "reason": "direct_disabled"}]
    assert [r["model"] for r in gem.requests] == ["gemini-3.5-flash-lite"]


def test_the_guards_run_every_page_and_count_the_calls_of_every_route(make):
    # page 1: OpenRouter answers on its second attempt; page 2: OpenRouter fails, the Gemini API answers
    extractor, http, gem = make(failed(503), ok(), failed(402))

    outcome = extract_pdf_pages(extractor, pages("text_menu_office.pdf"), PdfGuards())

    assert outcome.ok and outcome.stopped is None
    assert [page.raw_output["route"]["stage"] for page in outcome.pages] == [0, 2]
    assert [page.attempts for page in outcome.pages] == [2, 2]  # 2 OpenRouter calls; 1 OpenRouter + 1 Gemini
    assert outcome.model_attempts == 4 and len(http.posts) == 3 and len(gem.requests) == 1
    assert [page.raw_output["pdf"]["page"] for page in outcome.pages] == [1, 2]


def test_the_guards_stop_after_too_many_failed_pages_and_name_the_failure(make):
    extractor, http, _ = make(ok(text="{}"))
    document = pages("text_menu_office.pdf") * 2  # four pages

    outcome = extract_pdf_pages(extractor, document, PdfGuards(failed_pages=2))

    assert [page.failure for page in outcome.pages] == ["invalid_output", "invalid_output", "not_attempted", "not_attempted"]
    assert outcome.stopped == "too_many_failed_pages" and len(http.posts) == 2


def test_a_page_whose_routes_all_fail_is_a_model_call_failure_under_the_guards(make):
    extractor, _, _ = make(failed(402), gem=gemini_fake(direct=GeminiApiError(429), lite=GeminiApiError(429)))

    outcome = extract_pdf_pages(extractor, pages("text_menu_design.pdf"), PdfGuards())

    [page] = outcome.pages
    assert page.failure == "model_call_failed" and page.attempts == 3  # one call a route under the guards
    assert page.raw_output["route"]["stage"] == 4 and page.raw_output["pdf"]["page"] == 1


def test_no_page_starts_after_the_pdfs_deadline(make):
    extractor, http, _ = make()
    times = iter([0.0, 0.0, 500.0, 500.0, 500.0, 500.0])

    outcome = extract_pdf_pages(extractor, pages("text_menu_office.pdf"), PdfGuards(document_deadline_s=100),
                                clock=lambda: next(times))

    assert [page.failure for page in outcome.pages] == [None, "not_attempted"]
    assert outcome.stopped == "document_deadline" and len(http.posts) == 1


@pytest.mark.parametrize("raw_output, calls", [
    ({"attempts": 2, "route": {"stage": 0, "skipped": []}}, 2),
    ({"attempts": 1, "route": {"stage": 3, "skipped": [{"stage": 0, "attempts": 3}, {"stage": 2, "attempts": 1}]}}, 5),
    ({"attempts": 1, "route": {"stage": 2, "skipped": [{"stage": 0, "reason": "circuit_open"}]}}, 1),
    ({"attempts": 5, "route": {"stage": 4, "skipped": [{"stage": 0, "attempts": 3}, {"stage": 2, "attempts": 2}]}}, 5),
    ({"attempts": 2}, 2),  # the hybrid extractor's record, as before
    (None, 0),
])
def test_the_calls_of_a_page_are_those_of_every_route_it_tried(raw_output, calls):
    assert _attempts(raw_output) == calls


# ---- which PDF extractor ----


def test_the_pdf_extractor_follows_the_servers_extractor():
    routed = pdf_extractor_for(OpenRouterMenuExtractor(ROUTE, CLOVA))
    old = pdf_extractor_for(HybridMenuExtractor(SETTINGS, CLOVA, prompt="v2"))

    assert type(routed) is RoutedPdfMenuExtractor and routed.model_name == PRIMARY
    # MENU_EXTRACTOR=gemini with EXTRACTION_MODE=hybrid keeps the PDF extractor it had
    assert type(old) is PdfMenuExtractor and old.model_name == "gemini-3.5-flash-lite"
    assert old.pipeline_version == "bottlemap-menu-hybrid-prompthybrid-v2-thinking-medium-pdf"


@pytest.mark.parametrize("extractor", [MockMenuExtractor(), GeminiMenuExtractor(SETTINGS)])
def test_an_extractor_without_ocr_lines_has_no_pdf_path(extractor):
    with pytest.raises(extraction.ExtractionConfigError, match="PDF menus need MENU_EXTRACTOR=openrouter"):
        pdf_extractor_for(extractor)


def test_the_limited_copy_of_a_page_does_not_change_the_route_settings_object():
    extractor = RoutedPdfMenuExtractor(OpenRouterMenuExtractor(ROUTE, CLOVA))

    extractor.for_page(1, 30.0, 60.0)

    assert ROUTE == replace(ROUTE) and ROUTE.openrouter.max_attempts == 3 and json.dumps(ROUTE.openrouter.fallback_models)
