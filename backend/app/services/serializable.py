"""Running a request as one SERIALIZABLE transaction, retried as a whole on a write conflict
(schema guide 12, flow doc 17). Used by review-and-apply and the manual menu edits.

Each attempt opens a new session, runs the work, and commits. A write conflict rolls everything
back and runs the work again from the start, up to three attempts in total, then answers the
caller's `503 TEMPORARY_WRITE_CONFLICT`. Any other error is rolled back and raised without a retry.
The work must not have side effects outside the database.

A write conflict is a serialization failure, a deadlock, or a unique violation on a catalog
constraint. Catalog rows are shared by every bar, and requests for different bars do not wait
for each other's bar lock, so two of them can create the same brand or alias. PostgreSQL reports
that as a serialization failure when the request looked the row up first, as the catalog writer
does; the unique violation is retried as well so this does not depend on it. Either way the next
attempt sees the committed row and answers 409 or reuses it.
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
UNIQUE_VIOLATION = "23505"
# Unique constraints on catalog rows a request may create while a request for another bar does.
CATALOG_UNIQUE_CONSTRAINTS = {
    "brands_canonical_name_key",
    "uq_brand_aliases_brand_id_normalized_alias",
    "uq_product_aliases_product_id_normalized_alias",
}

# Replaced in tests so retries do not wait.
sleep = time.sleep


def write_conflict(message: str, details: dict | None = None) -> ApiError:
    return ApiError(503, "TEMPORARY_WRITE_CONFLICT", message, details=details)


def _is_retryable(error: DBAPIError) -> bool:
    sqlstate = getattr(error.orig, "sqlstate", None)
    if sqlstate in RETRYABLE_SQLSTATES:
        return True
    constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
    return sqlstate == UNIQUE_VIOLATION and constraint in CATALOG_UNIQUE_CONSTRAINTS


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
