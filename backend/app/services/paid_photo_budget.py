"""The server-wide daily limit on photos read through OpenRouter (I5-P19 follow-up).

The team has one OpenRouter key, without a spending limit of its own, so this count is the only
brake on what extraction spends in a day. Unlike the per-user limits of request_limits.py it must
survive a restart: a deployment restarts the process, and a brake that a deployment releases is
not one.

So the count is not kept only in memory. It is read from the extraction runs the server already
stores: a run whose `raw_output` says the photo was read at stage 0 or 1 (OpenRouter, the primary
or a fallback model) and that ended today (KST) is one paid photo. No table or column is added.

`DailyPaidBudget` holds today's count in memory, loaded from those rows on first use, after a
restart and when the KST day changes, and counted up by one for every photo sent to OpenRouter
after that. `try_reserve` takes a place before the call, so photos processed at the same time
cannot pass the limit together; `refund` gives it back when OpenRouter did not answer (nothing was
read and nothing is stored as a paid run).

Over the limit, nothing is refused: app.extraction.routed starts the photo at stage 2 (the Gemini
API) and records `daily_paid_limit` as the reason stage 0 was skipped. When the count cannot be
read (the database is unreachable), the photo is treated as over the limit: not knowing what was
spent is no reason to spend.

There is no operator reset. The count comes from stored runs, so it cannot be cleared without
rewriting them; to allow more photos today, raise OPENROUTER_DAILY_PHOTO_LIMIT and restart, which
keeps the count.
"""

import logging
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, date, datetime, time

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.models import ExtractionRun
from app.services.request_limits import KST, kst_date, utc_now

logger = logging.getLogger(__name__)

# app.extraction.routed: 0 is OpenRouter's primary model, 1 a fallback model.
PAID_STAGES = (0, 1)


def day_start(day: date) -> datetime:
    """Midnight KST at the start of `day`, in UTC."""
    return datetime.combine(day, time(0), tzinfo=KST).astimezone(UTC)


def paid_photos_query(since: datetime) -> Select[tuple[int]]:
    """Counts the runs that ended at or after `since` and were read through OpenRouter.

    A run that succeeded has the route in `raw_output.route`; a run that failed after OpenRouter
    answered (an answer that is not valid output is still billed) has it in `raw_output.output.route`
    (menu_import_processing puts the extractor's raw output under `output`).
    """
    stage = ExtractionRun.raw_output["route"]["stage"].as_integer()
    failed_stage = ExtractionRun.raw_output["output"]["route"]["stage"].as_integer()
    return select(func.count()).select_from(ExtractionRun).where(
        ExtractionRun.completed_at >= since, or_(stage.in_(PAID_STAGES), failed_stage.in_(PAID_STAGES))
    )


def count_paid_photos(session: Session, since: datetime) -> int:
    return session.scalar(paid_photos_query(since)) or 0


def stored_count_loader(session_factory: Callable[[], AbstractContextManager[Session]]) -> Callable[[datetime], int]:
    """`load` for DailyPaidBudget: opens a session of its own for each count."""

    def load(since: datetime) -> int:
        with session_factory() as session:
            return count_paid_photos(session, since)

    return load


class DailyPaidBudget:
    """Today's count of photos sent to OpenRouter, for the whole server. Thread-safe."""

    def __init__(self, limit: int, load: Callable[[datetime], int], clock: Callable[[], datetime] = utc_now) -> None:
        self.limit, self._load, self._clock = limit, load, clock
        self._lock = threading.Lock()
        self._day: date | None = None
        self._count = 0

    def _sync(self) -> bool:
        """Make `_count` today's count; False when it had to be read and could not be."""
        today = kst_date(self._clock())
        if self._day == today:
            return True
        try:
            self._count = self._load(day_start(today))
        except Exception:
            logger.exception("Could not count today's photos read through OpenRouter; treating the photo as over the limit")
            return False
        self._day = today
        return True

    def try_reserve(self) -> bool:
        """Take one place of today's limit for a photo about to be sent to OpenRouter."""
        with self._lock:
            if not self._sync() or self._count >= self.limit:
                return False
            self._count += 1
            return True

    def refund(self) -> None:
        """Give back the place of a photo OpenRouter did not answer."""
        with self._lock:
            # A place taken yesterday is not given back to today (the day's count was loaded anew).
            if self._day == kst_date(self._clock()) and self._count > 0:
                self._count -= 1

    def used(self) -> int | None:
        """Today's count, or None when it could not be read. For the log and for tests."""
        with self._lock:
            return self._count if self._sync() else None
