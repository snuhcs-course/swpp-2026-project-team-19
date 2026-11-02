"""Running a request as one SERIALIZABLE transaction, retried as a whole on a write conflict
(schema guide 12, flow doc 17). Used by review-and-apply and the manual menu edits.

Each attempt opens a new session, runs the work, and commits. A serialization failure or a
deadlock rolls everything back and runs the work again from the start, up to three attempts in
total, then answers the caller's `503 TEMPORARY_WRITE_CONFLICT`. Any other error is rolled back
and raised without a retry. The work must not have side effects outside the database.
"""

import logging
import random
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import TypeVar

from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.errors import ApiError

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], AbstractContextManager[Session]]
T = TypeVar("T")

MAX_ATTEMPTS = 3
# serialization_failure, deadlock_detected
RETRYABLE_SQLSTATES = {"40001", "40P01"}

# Replaced in tests so retries do not wait.
sleep = time.sleep


def write_conflict(message: str, details: dict | None = None) -> ApiError:
    return ApiError(503, "TEMPORARY_WRITE_CONFLICT", message, details=details)


def _is_retryable(error: DBAPIError) -> bool:
    return getattr(error.orig, "sqlstate", None) in RETRYABLE_SQLSTATES


def run_serializable(
    session_factory: SessionFactory, work: Callable[[Session], T], *, label: str, conflict: ApiError
) -> T:
    """work(session) in a transaction of its own, committed when it returns. `label` names the
    request in the log; `conflict` is raised after the last failed attempt."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        with session_factory() as session:
            try:
                result = work(session)
                session.commit()
                return result
            except DBAPIError as error:
                session.rollback()
                if not _is_retryable(error):
                    raise
                logger.info("%s: write conflict, attempt %d", label, attempt)
            except BaseException:
                session.rollback()
                raise
        if attempt < MAX_ATTEMPTS:
            sleep(random.uniform(0.05, 0.2) * attempt)
    raise conflict
