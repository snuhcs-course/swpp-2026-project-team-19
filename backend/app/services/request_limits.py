"""Daily per-user limits on requests that call an external API (spec 3.11.14).

Each kind of request (the certificate OCR of 3.11.12 and the NTS business verification of 3.11.2) has
its own count per token `sub` and its own daily limit (`DAILY_LIMITS`), and every count resets at
midnight KST. A caller acquires one
unit right before the external call and gets `429 RATE_LIMITED` when today's limit is used up,
so the external API is never called over the limit.

Menu photos (I5-A2, spec 4.1) are a third kind, counted in photos instead of requests: an upload
acquires one unit per photo, all of them or none (`acquire_units`), when it is accepted. Its limit
is a setting, MENU_PHOTO_DAILY_LIMIT (`menu_photo_daily_limit`).

The counts live in this process's memory, as the spec decides: a restart resets them, and they
are exact only while the API runs as a single process (backend/deploy/bottlemap-api.service).
An operator can also reset them without a restart (spec 3.11.19, `reset`).
`DailyRequestLimiter` is the seam for a shared store if that ever changes.
"""

import os
import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import Protocol

from app.core.errors import ApiError

KST = timezone(timedelta(hours=9), "KST")  # Korea has no daylight saving time

BUSINESS_CERTIFICATE_OCR = "business_certificate_ocr"
BUSINESS_VERIFICATION = "business_verification"

MENU_IMPORT_PHOTOS = "menu_import_photos"

BUSINESS_CERTIFICATE_OCR_DAILY_LIMIT = 5
BUSINESS_VERIFICATION_DAILY_LIMIT = 30
# The default; the limit in use is `menu_photo_daily_limit()`.
MENU_IMPORT_PHOTOS_DAILY_LIMIT = 30
MENU_PHOTO_DAILY_LIMIT_ENV = "MENU_PHOTO_DAILY_LIMIT"
DAILY_LIMITS: dict[str, int] = {
    BUSINESS_CERTIFICATE_OCR: BUSINESS_CERTIFICATE_OCR_DAILY_LIMIT,
    BUSINESS_VERIFICATION: BUSINESS_VERIFICATION_DAILY_LIMIT,
    MENU_IMPORT_PHOTOS: MENU_IMPORT_PHOTOS_DAILY_LIMIT,
}

DEFAULT_RATE_LIMITED_MESSAGE = "오늘 사업자등록 정보 확인 횟수를 모두 사용했습니다. 내일 다시 시도해 주세요."


def menu_photo_daily_limit() -> int:
    """Menu photos one user may upload per KST day: MENU_PHOTO_DAILY_LIMIT, or 30.

    Read on each call, like the other settings that need no restart to be tested; an invalid value
    is a RuntimeError, which stops the server at start-up (app.main checks it there).
    """
    raw = os.getenv(MENU_PHOTO_DAILY_LIMIT_ENV)
    if not raw:
        return MENU_IMPORT_PHOTOS_DAILY_LIMIT
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value <= 0:
        raise RuntimeError(f"{MENU_PHOTO_DAILY_LIMIT_ENV} must be a positive integer, got {raw!r}")
    return value


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


@dataclass(frozen=True)
class UnitsAcquisition:
    """The result of `acquire_units`. `remaining` is what is left of `day`'s limit: after the
    request when it was counted, and as it stands (nothing was counted) when it was refused."""

    day: date
    counted: bool
    remaining: int
    limit: int


class DailyRequestLimiter(Protocol):
    def acquire(self, subject: str, kind: str, now: datetime) -> Acquisition:
        """Count one request of `kind` for `subject` against the current KST day, unless that day's
        limit is used up."""
        ...

    def release(self, subject: str, kind: str, day: date) -> None:
        """Give back one unit counted against `day` (from `acquire`) when the external call was not
        made after all. Nothing happens once that day is over: its counts are gone."""
        ...

    def reset(self, subject: str | None, kind: str | None, now: datetime) -> int:
        """Clear today's counts of `subject` (every subject if None) for `kind` (every kind if None),
        and return how many counts were cleared."""
        ...

    def acquire_units(self, subject: str, kind: str, units: int, now: datetime) -> UnitsAcquisition:
        """Count `units` at once against the current KST day, or none of them when they do not all fit."""
        ...

    def release_units(self, subject: str, kind: str, day: date, units: int) -> None:
        """Give back `units` counted against `day` by `acquire_units`. Nothing happens once that day is over."""
        ...


class InMemoryDailyLimiter:
    """Counts in a dict guarded by a lock; the routes run in a thread pool. Holds only today's counts.

    Each kind has its limit from `DAILY_LIMITS`; `daily_limit` (for tests) sets one limit for every kind."""

    def __init__(self, daily_limit: int | None = None) -> None:
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

    def limit_for(self, kind: str) -> int:
        """Today's limit for `kind`. An unknown kind is a KeyError rather than an unlimited count."""
        if self.daily_limit is not None:
            return self.daily_limit
        if kind == MENU_IMPORT_PHOTOS:
            return menu_photo_daily_limit()
        return DAILY_LIMITS[kind]

    def acquire(self, subject: str, kind: str, now: datetime) -> Acquisition:
        with self._lock:
            day = self._roll_over(now)
            key = (subject, kind)
            used = self._counts.get(key, 0)
            if used >= self.limit_for(kind):
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

    def acquire_units(self, subject: str, kind: str, units: int, now: datetime) -> UnitsAcquisition:
        if units < 1:
            raise ValueError(f"units must be at least 1, got {units}")
        with self._lock:
            day = self._roll_over(now)
            key = (subject, kind)
            limit = self.limit_for(kind)
            used = self._counts.get(key, 0)
            if used + units > limit:
                return UnitsAcquisition(day, counted=False, remaining=max(0, limit - used), limit=limit)
            self._counts[key] = used + units
            return UnitsAcquisition(day, counted=True, remaining=limit - used - units, limit=limit)

    def release_units(self, subject: str, kind: str, day: date, units: int) -> None:
        with self._lock:
            # As `release`: units counted against a day that is over are not refunded from the new day.
            if day != self._day:
                return
            key = (subject, kind)
            left = self._counts.get(key, 0) - units
            if left > 0:
                self._counts[key] = left
            else:
                self._counts.pop(key, None)

    def reset(self, subject: str | None, kind: str | None, now: datetime) -> int:
        if kind is not None and kind not in DAILY_LIMITS:
            raise KeyError(kind)
        with self._lock:
            # Past midnight the counts are gone already; never clear a newer day's counts by an old one.
            self._roll_over(now)
            cleared = [
                key
                for key in self._counts
                if (subject is None or key[0] == subject) and (kind is None or key[1] == kind)
            ]
            for key in cleared:
                del self._counts[key]
            # A unit acquired before the reset and released after it is dropped from the new count,
            # so that request may get one extra call today; the spec accepts this.
            return len(cleared)

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


def acquire_menu_photos(limiter: DailyRequestLimiter, subject: str, photos: int, now: datetime) -> date:
    """Count the photos of one accepted menu upload against `subject`'s day (I5-A2, spec 4.1), and
    return the day for `release_units`.

    `photos` is what the upload asks the extraction to read: one per image, and one per page for a
    PDF. All of them are counted or none: when they do not all fit in what is left of today, the
    whole upload is refused with `429 RATE_LIMITED`, and `details` says how many would still fit
    (`remaining`), so the owner can upload fewer photos today.
    """
    acquisition = limiter.acquire_units(subject, MENU_IMPORT_PHOTOS, photos, now)
    if acquisition.counted:
        return acquisition.day
    if acquisition.remaining:
        message = (f"오늘 올릴 수 있는 메뉴 사진은 {acquisition.remaining}장 남았습니다. "
                   f"사진을 {acquisition.remaining}장 이하로 줄이거나 내일 다시 시도해 주세요.")
    else:
        message = f"오늘 올릴 수 있는 메뉴 사진 {acquisition.limit}장을 모두 사용했습니다. 내일 다시 시도해 주세요."
    raise ApiError(429, "RATE_LIMITED", message, details={
        "retryAfter": rfc3339_utc(reset_after(acquisition.day)),
        "dailyLimit": acquisition.limit,
        "remaining": acquisition.remaining,
        "requested": photos,
    })
