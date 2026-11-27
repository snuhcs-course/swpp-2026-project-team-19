"""The server-wide daily limit on photos read through OpenRouter (I5-P19 follow-up).

The count is read from stored extraction runs. These tests keep the runs in an in-memory SQLite
database (only the extraction_runs table), so they run without PostgreSQL; the PostgreSQL text of
the query is checked as text. OpenRouter and Gemini are fakes; no test calls a real API."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app import extraction
from app.adapters.openrouter_extraction import OpenRouterMenuExtractor
from app.api import deps
from app.extraction import gemini, hybrid, openrouter, routed
from app.extraction.routed import CircuitBreaker, extract_menu_routed
from app.models import ExtractionApproach, ExtractionRun, PipelineStatus
from app.services.paid_photo_budget import (
    DailyPaidBudget,
    count_paid_photos,
    day_start,
    paid_photos_query,
    stored_count_loader,
)
from app.services.request_limits import KST
from tests.test_hybrid_extraction_adapter import CLOVA, OCR_RESPONSE, jpeg
from tests.test_openrouter_extraction import ENV, FALLBACK, PRIMARY, ROUTE, FakeHttp, failed, gemini_fake, ok, set_openrouter_env

# 2026-11-26 12:00 KST; the KST day started at 2026-11-25 15:00 UTC.
NOON = datetime(2026, 11, 26, 3, tzinfo=UTC)
MIDNIGHT = datetime(2026, 11, 25, 15, tzinfo=UTC)


class Clock:
    def __init__(self, now=NOON):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def runs():
    """A session factory on an empty extraction_runs table."""
    engine = create_engine("sqlite://")
    ExtractionRun.__table__.create(engine)
    yield lambda: Session(engine)
    engine.dispose()


def store(runs, raw_output, completed_at=NOON, status=PipelineStatus.SUCCEEDED):
    """One finished run, as menu_import_processing stores it."""
    with runs() as session:
        session.add(ExtractionRun(
            menu_image_id=uuid4(), approach=ExtractionApproach.OCR_LLM, provider="naver-clova+openrouter",
            model_name=PRIMARY, pipeline_version="test", status=status, raw_output=raw_output, completed_at=completed_at))
        session.commit()


def route(stage):
    return {"route": {"stage": stage, "path": routed.PATHS.get(stage), "skipped": []}, "costUsd": 0.03}


def count(runs, since=MIDNIGHT):
    with runs() as session:
        return count_paid_photos(session, since)


# ---- counting the stored runs ----


def test_only_runs_read_through_openrouter_today_are_counted(runs):
    store(runs, route(0))                                                    # the primary model
    store(runs, route(1))                                                    # a fallback model
    store(runs, route(2))                                                    # the Gemini API: free
    store(runs, route(3))
    store(runs, {"model": "gemini-3.5-flash-lite", "rawOutput": {}})         # MENU_EXTRACTOR=gemini: no route
    store(runs, None, status=PipelineStatus.QUEUED, completed_at=None)       # not read yet
    store(runs, {"error": "Interrupted", "message": "restart"}, status=PipelineStatus.FAILED)
    # failed after OpenRouter answered (not valid output): billed, so counted
    store(runs, {"error": "ExtractionError", "message": "x", "output": {**route(0), "rawText": "{}"}},
          status=PipelineStatus.FAILED)
    # failed because every route failed: OpenRouter did not answer
    store(runs, {"error": "ExtractionError", "message": "x", "output": {"attempts": 5, "route": {"stage": 4}}},
          status=PipelineStatus.FAILED)

    assert count(runs) == 3


def test_the_day_is_the_kst_day(runs):
    store(runs, route(0), completed_at=MIDNIGHT - timedelta(seconds=1))  # 23:59:59 KST yesterday
    store(runs, route(0), completed_at=MIDNIGHT)                         # 00:00:00 KST today
    store(runs, route(0), completed_at=NOON)

    assert day_start(datetime(2026, 11, 26).date()) == MIDNIGHT
    assert count(runs) == 2 and count(runs, MIDNIGHT - timedelta(days=1)) == 3


def test_the_query_on_postgresql_reads_the_route_out_of_the_json_column():
    sql = str(paid_photos_query(MIDNIGHT).compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))

    assert "extraction_runs.completed_at >= '2026-11-25 15:00:00+00:00'" in sql
    assert "CAST(((extraction_runs.raw_output -> 'route') ->> 'stage') AS INTEGER) IN (0, 1)" in sql
    assert "CAST((((extraction_runs.raw_output -> 'output') -> 'route') ->> 'stage') AS INTEGER) IN (0, 1)" in sql


# ---- the budget ----


def test_the_last_place_is_given_and_the_next_photo_is_over_the_limit():
    budget = DailyPaidBudget(3, lambda since: 1, Clock())

    assert budget.used() == 1
    assert budget.try_reserve() and budget.try_reserve()  # the 2nd and 3rd photo of the day
    assert not budget.try_reserve() and budget.used() == 3


def test_a_place_is_given_back_when_openrouter_did_not_answer():
    budget = DailyPaidBudget(1, lambda since: 0, Clock())

    day = budget.try_reserve()
    assert day == NOON.astimezone(KST).date() and budget.try_reserve() is None
    budget.refund(day)
    assert budget.used() == 0 and budget.try_reserve() == day
    budget.refund(day)
    budget.refund(day)  # never below zero
    assert budget.used() == 0


def test_the_count_starts_over_when_the_kst_day_changes():
    clock, loads = Clock(MIDNIGHT - timedelta(seconds=1)), []

    def load(since):
        loads.append(since)
        return 2 if since == MIDNIGHT - timedelta(days=1) else 0

    budget = DailyPaidBudget(2, load, clock)
    assert not budget.try_reserve()  # yesterday's two places are used

    clock.now = MIDNIGHT
    assert budget.try_reserve() and budget.used() == 1
    assert loads == [MIDNIGHT - timedelta(days=1), MIDNIGHT]  # read once a day, not for every photo


def test_a_place_taken_yesterday_is_not_given_back_to_today():
    clock = Clock(MIDNIGHT - timedelta(seconds=1))
    budget = DailyPaidBudget(5, lambda since: 0, clock)
    yesterday = budget.try_reserve()  # a call that started before midnight

    clock.now = MIDNIGHT
    today = budget.try_reserve()  # a photo after midnight takes today's place
    assert today != yesterday and budget.used() == 1
    budget.refund(yesterday)  # the old call fails after midnight: today's place stays taken
    assert budget.used() == 1
    budget.refund(today)
    assert budget.used() == 0


def test_a_refund_after_the_day_changed_but_before_the_count_was_read_again_gives_nothing_back():
    clock = Clock(MIDNIGHT - timedelta(seconds=1))
    budget = DailyPaidBudget(5, lambda since: 1, clock)
    yesterday = budget.try_reserve()

    clock.now = MIDNIGHT
    budget.refund(yesterday)  # nothing has read today's count yet

    assert budget.used() == 1  # today's count, as loaded


def test_when_the_count_cannot_be_read_the_photo_is_over_the_limit_until_it_can(caplog):
    answers = [RuntimeError("database is down"), 4]

    def load(since):
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    budget = DailyPaidBudget(10, load, Clock())

    with caplog.at_level(logging.ERROR, logger="app.services.paid_photo_budget"):
        assert not budget.try_reserve()
    assert "Could not count today's photos read through OpenRouter" in caplog.text
    assert budget.try_reserve() and budget.used() == 5  # read again on the next photo


def test_the_count_survives_a_restart(runs):
    for _ in range(4):
        store(runs, route(0))
    store(runs, route(0), completed_at=MIDNIGHT - timedelta(hours=1))  # yesterday

    # A restart is a new process: a new budget with nothing in memory, on the same stored runs.
    restarted = DailyPaidBudget(5, stored_count_loader(runs), Clock())

    assert restarted.used() == 4
    assert restarted.try_reserve() and not restarted.try_reserve()


# ---- the ladder ----


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    monkeypatch.setattr(openrouter, "sleep", lambda seconds: None)
    monkeypatch.setattr(gemini, "sleep", lambda seconds: None)
    monkeypatch.setattr(hybrid, "call_ocr", lambda settings, image, mime_type, client=None: {
        "response": OCR_RESPONSE, "sentSize": [1000, 2000], "latencyMs": 900, "attempts": 1})


def read(http, budget, gem=None, breaker=None):
    return extract_menu_routed(jpeg(), "image/jpeg", CLOVA, ROUTE, breaker or CircuitBreaker(), budget=budget,
                               http_client=http, gemini_client=gem or gemini_fake())["meta"]


def test_under_the_limit_photos_go_to_openrouter_and_are_counted():
    http, budget = FakeHttp(ok()), DailyPaidBudget(2, lambda since: 0, Clock())

    stages = [read(http, budget)["route"]["stage"] for _ in range(2)]

    assert stages == [0, 0] and len(http.posts) == 2 and budget.used() == 2


def test_over_the_limit_the_photo_starts_at_the_gemini_api_and_the_log_says_why(caplog):
    http, gem, budget = FakeHttp(ok()), gemini_fake(), DailyPaidBudget(2, lambda since: 2, Clock())

    with caplog.at_level(logging.WARNING, logger="app.extraction.routed"):
        meta = read(http, budget, gem)

    assert http.posts == [] and len(gem.requests) == 1  # OpenRouter is not called: nothing is spent
    assert (meta["route"]["stage"], meta["route"]["path"], meta["costUsd"]) == (2, "gemini-direct", None)
    assert meta["route"]["skipped"] == [{"stage": 0, "reason": "daily_paid_limit", "limit": 2}]
    assert "extraction route stage=0 skipped: daily_paid_limit" in caplog.text
    assert "stage=2 path=gemini-direct" in caplog.text and "skipped=0:daily_paid_limit" in caplog.text
    assert budget.used() == 2


@pytest.mark.parametrize("second", ["http 503", "connection reset"])
def test_a_cut_answer_that_was_billed_keeps_its_place_when_the_second_call_fails(second):
    retry = failed(503) if second == "http 503" else httpx.ReadError("connection reset")
    http = FakeHttp(ok(text='{"items": [', finish="length", cost=0.2), retry)
    budget = DailyPaidBudget(5, lambda since: 0, Clock())

    meta = read(http, budget)

    assert meta["route"]["stage"] == 2 and budget.used() == 1  # the cut answer was paid for: no refund
    assert meta["route"]["skipped"][0]["billedUsd"] == 0.2
    assert meta["route"]["skipped"][0]["reason"] == "ModelCallError"


def test_a_failed_call_without_a_billed_answer_still_gives_its_place_back():
    http, budget = FakeHttp(failed(503)), DailyPaidBudget(5, lambda since: 0, Clock())

    meta = read(http, budget)

    assert budget.used() == 0 and "billedUsd" not in meta["route"]["skipped"][0]


def test_the_photo_after_the_last_place_is_the_first_one_sent_to_the_gemini_api():
    http, budget = FakeHttp(ok()), DailyPaidBudget(3, lambda since: 1, Clock())

    stages = [read(http, budget)["route"]["stage"] for _ in range(4)]

    assert stages == [0, 0, 2, 2] and len(http.posts) == 2


def test_the_next_day_photos_go_to_openrouter_again():
    clock = Clock(MIDNIGHT - timedelta(seconds=1))
    http, budget = FakeHttp(ok()), DailyPaidBudget(1, lambda since: 0, clock)

    before = [read(http, budget)["route"]["stage"] for _ in range(2)]
    clock.now = MIDNIGHT
    after = read(http, budget)["route"]["stage"]

    assert (before, after) == ([0, 2], 0)


def test_a_failed_openrouter_call_does_not_use_up_a_place():
    budget = DailyPaidBudget(1, lambda since: 0, Clock())

    assert read(FakeHttp(failed(402)), budget)["route"]["stage"] == 2
    assert budget.used() == 0
    assert read(FakeHttp(ok()), budget)["route"]["stage"] == 0 and budget.used() == 1


def test_an_answer_that_is_not_valid_output_was_paid_for_and_keeps_its_place():
    budget = DailyPaidBudget(5, lambda since: 0, Clock())

    with pytest.raises(extraction.InvalidModelOutputError):
        read(FakeHttp(ok(text="{}")), budget)

    assert budget.used() == 1


def test_a_fallback_model_uses_a_place_too():
    budget = DailyPaidBudget(5, lambda since: 0, Clock())

    assert read(FakeHttp(ok(model=FALLBACK)), budget)["route"]["stage"] == 1 and budget.used() == 1


def test_a_paused_openrouter_takes_no_place():
    breaker, budget = CircuitBreaker(1, 600), DailyPaidBudget(5, lambda since: 0, Clock())
    read(FakeHttp(failed(402)), budget, breaker=breaker)

    meta = read(FakeHttp(ok()), budget, breaker=breaker)

    assert meta["route"]["skipped"] == [{"stage": 0, "reason": "circuit_open"}] and budget.used() == 0


def test_without_a_budget_there_is_no_daily_limit():
    http = FakeHttp(ok())

    assert [read(http, None)["route"]["stage"] for _ in range(3)] == [0, 0, 0]


def test_runs_stored_by_the_server_are_what_a_restarted_server_counts(runs, monkeypatch):
    # Read photos through the adapter, store each raw_output as menu_import_processing does, restart.
    extractor = OpenRouterMenuExtractor(ROUTE, CLOVA, budget=DailyPaidBudget(3, stored_count_loader(runs), Clock()))
    http = FakeHttp(ok())
    monkeypatch.setattr(openrouter.httpx, "post", http.post)
    monkeypatch.setattr(gemini, "make_client", lambda settings: gemini_fake())
    for _ in range(4):
        store(runs, extractor.extract(jpeg(), "image/jpeg", None).raw_output)
    assert len(http.posts) == 3 and count(runs) == 3  # the 4th photo went to the Gemini API

    restarted = OpenRouterMenuExtractor(ROUTE, CLOVA, budget=DailyPaidBudget(3, stored_count_loader(runs), Clock()))
    after = restarted.extract(jpeg(), "image/jpeg", None).raw_output

    assert after["route"]["stage"] == 2 and after["route"]["skipped"][0]["reason"] == "daily_paid_limit"
    assert len(http.posts) == 3  # still nothing more spent after the restart


# ---- the setting ----


@pytest.fixture
def env(monkeypatch):
    for name in (*ENV, "OPENROUTER_DAILY_PHOTO_LIMIT"):
        monkeypatch.delenv(name, raising=False)
    deps.get_menu_extractor.cache_clear()
    yield monkeypatch
    deps.get_menu_extractor.cache_clear()


def test_the_server_gives_the_extractor_a_budget_of_300_photos_unless_the_setting_says_otherwise(env):
    set_openrouter_env(env)
    assert deps.get_menu_extractor().budget.limit == 300

    deps.get_menu_extractor.cache_clear()
    env.setenv("OPENROUTER_DAILY_PHOTO_LIMIT", "120")
    extractor = deps.get_menu_extractor()

    assert isinstance(extractor.budget, DailyPaidBudget) and extractor.budget.limit == 120
    assert extractor.route.daily_paid_limit == 120


@pytest.mark.parametrize("value", ["0", "-1", "plenty"])
def test_an_invalid_limit_stops_the_server_at_start_up(env, value):
    set_openrouter_env(env)
    env.setenv("OPENROUTER_DAILY_PHOTO_LIMIT", value)

    with pytest.raises(RuntimeError, match="OPENROUTER_DAILY_PHOTO_LIMIT must be a positive int"):
        deps.get_menu_extractor()
