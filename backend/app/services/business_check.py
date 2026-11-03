"""The NTS business registration check before applying (API spec 3.11.16), and the recent matches an
application may use instead of calling NTS again (3.11.2, step 5).

Both this check and applying call NTS through `call_nts`, so they count against one daily limit
(3.11.14): each NTS answer tells whether the three values belong together, so counting them apart would
give twice the guesses at someone else's number.

A match is remembered for its caller (token `sub`) and its exact three values for `RECENT_CHECK_TTL`.
An application with the same values in that time uses it instead of calling NTS, so checking first
and then applying costs one unit, not two. Only matches are remembered: after a mismatch or an
unavailable check, applying asks NTS again. Like the limiter, the store lives in this process's memory:
a restart forgets it, and applying then calls NTS again.
"""

import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.adapters.business_verification import BusinessCheck, BusinessVerificationUnavailable, BusinessVerifier
from app.core.errors import validation_failed
from app.core.security import Principal
from app.models import BusinessStatus
from app.schemas.owner_application import BusinessFieldsInput
from app.services.request_limits import BUSINESS_VERIFICATION, DailyRequestLimiter, acquire_or_raise, kst_date

RECENT_CHECK_TTL = timedelta(minutes=30)


@dataclass(frozen=True)
class RecentMatch:
    business_status: BusinessStatus | None
    checked_at: datetime


class RecentBusinessChecks:
    """Matches from the check before applying, per caller and values, for `RECENT_CHECK_TTL`. Guarded by
    a lock; the routes run in a thread pool. Expired entries are dropped whenever one is added, so the
    store holds at most the daily limit of entries per caller."""

    def __init__(self, ttl: timedelta = RECENT_CHECK_TTL) -> None:
        self.ttl = ttl
        self._lock = threading.Lock()
        self._matches: dict[tuple[str, str, str, date], RecentMatch] = {}

    def remember(self, subject: str, fields: BusinessFieldsInput, match: RecentMatch) -> None:
        with self._lock:
            self._matches = {
                key: kept for key, kept in self._matches.items() if kept.checked_at + self.ttl > match.checked_at
            }
            self._matches[_key(subject, fields)] = match

    def recall(self, subject: str, fields: BusinessFieldsInput, now: datetime) -> RecentMatch | None:
        with self._lock:
            match = self._matches.get(_key(subject, fields))
        return match if match is not None and match.checked_at + self.ttl > now else None


def _key(subject: str, fields: BusinessFieldsInput) -> tuple[str, str, str, date]:
    return subject, fields.businessRegistrationNumber, fields.representativeName, fields.openingDate


def check_opening_date(fields: BusinessFieldsInput, now: datetime) -> None:
    if fields.openingDate > kst_date(now):
        raise validation_failed("openingDate", "DATE_IN_FUTURE", "개업일자는 오늘 이후일 수 없습니다.")


def call_nts(
    principal: Principal,
    fields: BusinessFieldsInput,
    verifier: BusinessVerifier,
    limiter: DailyRequestLimiter,
    now: datetime,
) -> BusinessCheck | None:
    """NTS's answer, counted against today's limit (`429` when it is used up); None when NTS could not
    answer, which still counts."""
    acquire_or_raise(limiter, principal.subject, BUSINESS_VERIFICATION, now)
    try:
        return verifier.verify(fields.businessRegistrationNumber, fields.representativeName, fields.openingDate)
    except BusinessVerificationUnavailable:
        return None


def check_business(
    principal: Principal,
    fields: BusinessFieldsInput,
    *,
    verifier: BusinessVerifier | None,
    limiter: DailyRequestLimiter,
    recent: RecentBusinessChecks,
    now: datetime,
) -> str:
    """The check before applying (spec 3.11.16): `matched`, `not_matched` or `unavailable`. Creates
    nothing; a match is remembered for applying. Without a verifier nothing is called or counted."""
    check_opening_date(fields, now)
    if verifier is None:
        return "unavailable"
    check = call_nts(principal, fields, verifier, limiter, now)
    if check is None:
        return "unavailable"
    if not check.matched:
        return "not_matched"
    recent.remember(principal.subject, fields, RecentMatch(check.business_status, now))
    return "matched"
