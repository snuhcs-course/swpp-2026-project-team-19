"""Daily per-user request limits reset at midnight KST (spec 3.11.14)."""

import threading
from datetime import UTC, date, datetime

import pytest

from app.core.errors import ApiError
from app.services.request_limits import (
    BUSINESS_CERTIFICATE_OCR,
    DAILY_LIMIT,
    InMemoryDailyLimiter,
    acquire_or_raise,
    kst_date,
    next_reset,
    rfc3339_utc,
    utc_now,
)

# 2026-10-28 23:59:59 KST and the next second, 2026-10-29 00:00:00 KST.
BEFORE_MIDNIGHT = datetime(2026, 10, 28, 14, 59, 59, tzinfo=UTC)
AT_MIDNIGHT = datetime(2026, 10, 28, 15, 0, 0, tzinfo=UTC)
OTHER = "business_verification"


def test_kst_day_and_next_reset():
    assert kst_date(BEFORE_MIDNIGHT) == date(2026, 10, 28)
    assert kst_date(AT_MIDNIGHT) == date(2026, 10, 29)
    # 09:00 UTC is 18:00 KST the same day; 16:00 UTC is already the next day in Korea.
    assert next_reset(datetime(2026, 10, 28, 9, 0, tzinfo=UTC)) == AT_MIDNIGHT
    assert next_reset(datetime(2026, 10, 28, 16, 0, tzinfo=UTC)) == datetime(2026, 10, 29, 15, 0, tzinfo=UTC)
    assert next_reset(BEFORE_MIDNIGHT) == AT_MIDNIGHT
    assert rfc3339_utc(AT_MIDNIGHT) == "2026-10-28T15:00:00Z"
    assert utc_now().tzinfo is UTC


def test_limit_per_subject_and_kind():
    limiter = InMemoryDailyLimiter()
    assert DAILY_LIMIT == 5
    days = [limiter.acquire("a", BUSINESS_CERTIFICATE_OCR, BEFORE_MIDNIGHT) for _ in range(6)]
    assert days == [date(2026, 10, 28)] * 5 + [None]
    # The refused request is not counted.
    assert limiter.used("a", BUSINESS_CERTIFICATE_OCR, BEFORE_MIDNIGHT) == 5
    # Another user, and another kind for the same user, have their own counts.
    assert limiter.acquire("b", BUSINESS_CERTIFICATE_OCR, BEFORE_MIDNIGHT)
    assert limiter.acquire("a", OTHER, BEFORE_MIDNIGHT)


def test_counts_reset_at_midnight_kst():
    limiter = InMemoryDailyLimiter(daily_limit=1)
    assert limiter.acquire("a", BUSINESS_CERTIFICATE_OCR, BEFORE_MIDNIGHT) == date(2026, 10, 28)
    assert limiter.acquire("a", BUSINESS_CERTIFICATE_OCR, BEFORE_MIDNIGHT) is None
    assert limiter.acquire("a", BUSINESS_CERTIFICATE_OCR, AT_MIDNIGHT) == date(2026, 10, 29)
    # A request that read the clock before midnight but arrives late counts against the new day.
    assert limiter.acquire("a", BUSINESS_CERTIFICATE_OCR, BEFORE_MIDNIGHT) is None
    assert limiter.used("a", BUSINESS_CERTIFICATE_OCR, AT_MIDNIGHT) == 1


def test_release_gives_back_one_unit():
    limiter = InMemoryDailyLimiter(daily_limit=2)
    day = limiter.acquire("a", BUSINESS_CERTIFICATE_OCR, BEFORE_MIDNIGHT)
    limiter.acquire("a", BUSINESS_CERTIFICATE_OCR, BEFORE_MIDNIGHT)
    limiter.release("a", BUSINESS_CERTIFICATE_OCR, day)
    assert limiter.used("a", BUSINESS_CERTIFICATE_OCR, BEFORE_MIDNIGHT) == 1
    limiter.release("a", BUSINESS_CERTIFICATE_OCR, day)
    limiter.release("a", BUSINESS_CERTIFICATE_OCR, day)  # nothing left: stays at 0
    assert limiter.used("a", BUSINESS_CERTIFICATE_OCR, BEFORE_MIDNIGHT) == 0


def test_release_after_midnight_does_not_refund_the_new_day():
    """Codex review: a unit acquired before midnight and given back after it must not lower the new day's count."""
    limiter = InMemoryDailyLimiter(daily_limit=1)
    old_day = limiter.acquire("a", BUSINESS_CERTIFICATE_OCR, BEFORE_MIDNIGHT)
    assert limiter.acquire("a", BUSINESS_CERTIFICATE_OCR, AT_MIDNIGHT) == date(2026, 10, 29)

    limiter.release("a", BUSINESS_CERTIFICATE_OCR, old_day)

    assert limiter.used("a", BUSINESS_CERTIFICATE_OCR, AT_MIDNIGHT) == 1
    assert limiter.acquire("a", BUSINESS_CERTIFICATE_OCR, AT_MIDNIGHT) is None


def test_a_late_acquire_counted_against_the_new_day_is_released_from_it():
    limiter = InMemoryDailyLimiter(daily_limit=2)
    limiter.acquire("b", BUSINESS_CERTIFICATE_OCR, AT_MIDNIGHT)  # rolls the limiter to the new day
    late = limiter.acquire("a", BUSINESS_CERTIFICATE_OCR, BEFORE_MIDNIGHT)
    assert late == date(2026, 10, 29)
    limiter.release("a", BUSINESS_CERTIFICATE_OCR, late)
    assert limiter.used("a", BUSINESS_CERTIFICATE_OCR, AT_MIDNIGHT) == 0


def test_concurrent_requests_never_exceed_the_limit():
    limiter = InMemoryDailyLimiter()
    results: list[bool] = []
    barrier = threading.Barrier(20)

    def call():
        barrier.wait()
        results.append(limiter.acquire("a", BUSINESS_CERTIFICATE_OCR, BEFORE_MIDNIGHT) is not None)

    threads = [threading.Thread(target=call) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results.count(True) == DAILY_LIMIT


def test_acquire_or_raise_returns_429_with_the_next_reset():
    limiter = InMemoryDailyLimiter(daily_limit=1)
    assert acquire_or_raise(limiter, "a", BUSINESS_CERTIFICATE_OCR, BEFORE_MIDNIGHT) == date(2026, 10, 28)
    with pytest.raises(ApiError) as caught:
        acquire_or_raise(limiter, "a", BUSINESS_CERTIFICATE_OCR, BEFORE_MIDNIGHT)
    error = caught.value
    assert (error.status_code, error.code) == (429, "RATE_LIMITED")
    assert error.details == {"retryAfter": "2026-10-28T15:00:00Z"}
    assert error.message == "오늘 사업자등록 정보 확인 횟수를 모두 사용했습니다. 내일 다시 시도해 주세요."
