"""Daily per-user limits on requests that call an external API (spec 3.11.14).

Each kind of request (certificate OCR now; the NTS business verification of 3.11.2 later) has
its own count per token `sub`, and every count resets at midnight KST. A caller acquires one
unit right before the external call and gets `429 RATE_LIMITED` when today's limit is used up,
so the external API is never called over the limit.

The counts live in this process's memory, as the spec decides: a restart resets them, and they
are exact only while the API runs as a single process (backend/deploy/bottlemap-api.service).
`DailyRequestLimiter` is the seam for a shared store if that ever changes.
"""

import threading
from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import Protocol

from app.core.errors import ApiError

KST = timezone(timedelta(hours=9), "KST")  # Korea has no daylight saving time
DAILY_LIMIT = 5

BUSINESS_CERTIFICATE_OCR = "business_certificate_ocr"

DEFAULT_RATE_LIMITED_MESSAGE = "오늘 사업자등록 정보 확인 횟수를 모두 사용했습니다. 내일 다시 시도해 주세요."


def utc_now() -> datetime:
    return datetime.now(UTC)


def kst_date(now: datetime) -> date:
    """The calendar day in Korea at `now` (an aware datetime)."""
    return now.astimezone(KST).date()


def next_reset(now: datetime) -> datetime:
    """The next midnight KST after `now`, in UTC."""
    tomorrow = kst_date(now) + timedelta(days=1)
    return datetime.combine(tomorrow, time(0), tzinfo=KST).astimezone(UTC)


def rfc3339_utc(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class DailyRequestLimiter(Protocol):
    def acquire(self, subject: str, kind: str, now: datetime) -> bool:
        """Count one request of `kind` for `subject` today (KST). False, and nothing counted, at the limit."""
        ...

    def release(self, subject: str, kind: str, now: datetime) -> None:
        """Give back one unit acquired today when the external call was not made after all."""
        ...


class InMemoryDailyLimiter:
    """Counts in a dict guarded by a lock; the routes run in a thread pool. Holds only today's counts."""

    def __init__(self, daily_limit: int = DAILY_LIMIT) -> None:
        self.daily_limit = daily_limit
        self._lock = threading.Lock()
        self._day: date | None = None
        self._counts: dict[tuple[str, str], int] = {}

    def _roll_over(self, now: datetime) -> None:
        day = kst_date(now)
        # A request that read the clock just before midnight but got here after a newer one
        # counts against the newer day instead of wiping it.
        if self._day is None or day > self._day:
            self._day = day
            self._counts.clear()

    def acquire(self, subject: str, kind: str, now: datetime) -> bool:
        with self._lock:
            self._roll_over(now)
            key = (subject, kind)
            used = self._counts.get(key, 0)
            if used >= self.daily_limit:
                return False
            self._counts[key] = used + 1
            return True

    def release(self, subject: str, kind: str, now: datetime) -> None:
        with self._lock:
            self._roll_over(now)
            key = (subject, kind)
            used = self._counts.get(key, 0)
            if used > 1:
                self._counts[key] = used - 1
            else:
                self._counts.pop(key, None)

    def used(self, subject: str, kind: str, now: datetime) -> int:
        """Today's count, for tests and diagnostics."""
        with self._lock:
            self._roll_over(now)
            return self._counts.get((subject, kind), 0)


def rate_limited(now: datetime, message: str = DEFAULT_RATE_LIMITED_MESSAGE) -> ApiError:
    return ApiError(429, "RATE_LIMITED", message, details={"retryAfter": rfc3339_utc(next_reset(now))})


def acquire_or_raise(
    limiter: DailyRequestLimiter,
    subject: str,
    kind: str,
    now: datetime,
    message: str = DEFAULT_RATE_LIMITED_MESSAGE,
) -> None:
    """Count one request, or raise `429 RATE_LIMITED` with `details.retryAfter` (next midnight KST, UTC)."""
    if not limiter.acquire(subject, kind, now):
        raise rate_limited(now, message)
