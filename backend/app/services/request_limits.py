"""Daily per-user limits on requests that call an external API (spec 3.11.14).

Each kind of request (the certificate OCR of 3.11.12 and the NTS business verification of 3.11.2) has
its own count per token `sub`, and every count resets at midnight KST. A caller acquires one
unit right before the external call and gets `429 RATE_LIMITED` when today's limit is used up,
so the external API is never called over the limit.

The counts live in this process's memory, as the spec decides: a restart resets them, and they
are exact only while the API runs as a single process (backend/deploy/bottlemap-api.service).
`DailyRequestLimiter` is the seam for a shared store if that ever changes.
"""

import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import Protocol

from app.core.errors import ApiError

KST = timezone(timedelta(hours=9), "KST")  # Korea has no daylight saving time
DAILY_LIMIT = 5

BUSINESS_CERTIFICATE_OCR = "business_certificate_ocr"
BUSINESS_VERIFICATION = "business_verification"

DEFAULT_RATE_LIMITED_MESSAGE = "오늘 사업자등록 정보 확인 횟수를 모두 사용했습니다. 내일 다시 시도해 주세요."


def utc_now() -> datetime:
    return datetime.now(UTC)


def kst_date(now: datetime) -> date:
    """The calendar day in Korea at `now` (an aware datetime)."""
    return now.astimezone(KST).date()


def reset_after(day: date) -> datetime:
    """The midnight KST that ends the KST day `day`, in UTC."""
    return datetime.combine(day + timedelta(days=1), time(0), tzinfo=KST).astimezone(UTC)


def next_reset(now: datetime) -> datetime:
    """The next midnight KST after `now`, in UTC."""
    return reset_after(kst_date(now))


def rfc3339_utc(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class Acquisition:
    """The result of `acquire`. `day` is the KST day the request was checked against, which is
    the limiter's current day and can be later than the caller's clock near midnight; `counted`
    is False, with nothing counted, when that day's limit was already used up."""

    day: date
    counted: bool


class DailyRequestLimiter(Protocol):
    def acquire(self, subject: str, kind: str, now: datetime) -> Acquisition:
        """Count one request of `kind` for `subject` against the current KST day, unless that day's
        limit is used up."""
        ...

    def release(self, subject: str, kind: str, day: date) -> None:
        """Give back one unit counted against `day` (from `acquire`) when the external call was not
        made after all. Nothing happens once that day is over: its counts are gone."""
        ...


class InMemoryDailyLimiter:
    """Counts in a dict guarded by a lock; the routes run in a thread pool. Holds only today's counts."""

    def __init__(self, daily_limit: int = DAILY_LIMIT) -> None:
        self.daily_limit = daily_limit
        self._lock = threading.Lock()
        self._day: date | None = None
        self._counts: dict[tuple[str, str], int] = {}

    def _roll_over(self, now: datetime) -> date:
        """Move to `now`'s KST day if it is newer, and return the current day."""
        day = kst_date(now)
        # A request that read the clock just before midnight but got here after a newer one
        # counts against the newer day instead of wiping it.
        if self._day is None or day > self._day:
            self._day = day
            self._counts.clear()
        return self._day

    def acquire(self, subject: str, kind: str, now: datetime) -> Acquisition:
        with self._lock:
            day = self._roll_over(now)
            key = (subject, kind)
            used = self._counts.get(key, 0)
            if used >= self.daily_limit:
                return Acquisition(day, counted=False)
            self._counts[key] = used + 1
            return Acquisition(day, counted=True)

    def release(self, subject: str, kind: str, day: date) -> None:
        with self._lock:
            # A unit counted against a day that is over must not be refunded from the new day.
            if day != self._day:
                return
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


def rate_limited(day: date, message: str = DEFAULT_RATE_LIMITED_MESSAGE) -> ApiError:
    """`429 RATE_LIMITED` for a request refused because `day`'s limit is used up."""
    return ApiError(429, "RATE_LIMITED", message, details={"retryAfter": rfc3339_utc(reset_after(day))})


def acquire_or_raise(
    limiter: DailyRequestLimiter,
    subject: str,
    kind: str,
    now: datetime,
    message: str = DEFAULT_RATE_LIMITED_MESSAGE,
) -> date:
    """Count one request and return the day for `release`, or raise `429 RATE_LIMITED` with
    `details.retryAfter`: the end of the day that refused it (midnight KST, UTC). That day comes
    from the limiter, not from `now`, which may be just before a midnight the limiter has passed."""
    acquisition = limiter.acquire(subject, kind, now)
    if not acquisition.counted:
        raise rate_limited(acquisition.day, message)
    return acquisition.day
