"""Daily counts of customer searches (API spec 3.10.6), for the popular whiskies (3.17) and for
finding what the catalogue is missing.

Each count is one row per key and Seoul date, raised by 1 per search. A write that creates a row
also deletes the rows past their retention in the same transaction, so no scheduled job is needed;
the ranking filters by date, so rows waiting to be deleted never change it.

A failed write is rolled back and logged, and the search still answers 200.
"""

import logging
import re
from collections.abc import Callable
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import ProductSearchCount, SearchSource, UnmatchedSearchQuery

logger = logging.getLogger(__name__)

PRODUCT_COUNT_RETENTION_DAYS = 90
UNMATCHED_QUERY_RETENTION_DAYS = 30
MAX_NEW_UNMATCHED_QUERIES_PER_DAY = 1_000
UNMATCHED_QUERY_MAX_LENGTH = 200  # unmatched_search_queries.normalized_query
# Serializes the creation of unmatched-query rows, so concurrent searches cannot pass the daily
# cap together. Taken only by searches that would create a row. Any constant unused elsewhere.
UNMATCHED_QUERY_LOCK_KEY = 3_100_600_001

# Phone numbers and other long numbers, once "-" and "." are dropped. Ages and vintages are shorter.
_LONG_NUMBER = re.compile(r"\d{7,}")


def first_kept_date(today: date, days: int) -> date:
    """The oldest date of the `days` days ending with `today`, `today` included."""
    return today - timedelta(days=days - 1)


def is_storable_unmatched_query(trimmed: str, normalized: str) -> bool:
    """False for what may be an email or a phone number, and for what does not fit the column."""
    if "@" in trimmed:
        return False
    if _LONG_NUMBER.search(normalized.replace("-", "").replace(".", "")):
        return False
    return len(normalized) <= UNMATCHED_QUERY_MAX_LENGTH


def _count_product(session: Session, today: date, product_id: UUID, source: SearchSource) -> None:
    table = ProductSearchCount.__table__
    key = (table.c.search_date == today) & (table.c.product_id == product_id) & (table.c.source == source)
    if session.execute(update(table).where(key).values(search_count=table.c.search_count + 1)).rowcount:
        return
    # A concurrent search may create the row between the update and here.
    session.execute(
        insert(table)
        .values(search_date=today, product_id=product_id, source=source, search_count=1)
        .on_conflict_do_update(
            index_elements=[table.c.search_date, table.c.product_id, table.c.source],
            set_={"search_count": table.c.search_count + 1},
        )
    )
    first_kept = first_kept_date(today, PRODUCT_COUNT_RETENTION_DAYS)
    session.execute(delete(table).where(table.c.search_date < first_kept))


def _count_unmatched(session: Session, today: date, normalized: str) -> None:
    table = UnmatchedSearchQuery.__table__
    key = (table.c.search_date == today) & (table.c.normalized_query == normalized)
    if session.execute(update(table).where(key).values(search_count=table.c.search_count + 1)).rowcount:
        return
    # Held until commit. Each statement below sees the rows other searches committed before we got it.
    session.execute(select(func.pg_advisory_xact_lock(UNMATCHED_QUERY_LOCK_KEY)))
    created = session.scalar(select(func.count()).select_from(table).where(table.c.search_date == today))
    if created >= MAX_NEW_UNMATCHED_QUERIES_PER_DAY:
        return
    session.execute(
        insert(table)
        .values(search_date=today, normalized_query=normalized, search_count=1)
        .on_conflict_do_update(
            index_elements=[table.c.search_date, table.c.normalized_query],
            set_={"search_count": table.c.search_count + 1},
        )
    )
    first_kept = first_kept_date(today, UNMATCHED_QUERY_RETENTION_DAYS)
    session.execute(delete(table).where(table.c.search_date < first_kept))


def _record(session: Session, write: Callable[[], None]) -> None:
    """Run `write` and commit; on any failure roll back and log, never raise."""
    try:
        write()
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Could not record a search count; the search was answered anyway")


def record_product_search(session: Session, today: date, product_id: UUID, source: SearchSource) -> None:
    """Count a search that resolved to exactly one product. Commits the session."""
    _record(session, lambda: _count_product(session, today, product_id, source))


def record_unmatched_search(session: Session, today: date, trimmed: str, normalized: str) -> None:
    """Count a query that matched no product, unless the protection rules leave it out. Commits the session."""
    if is_storable_unmatched_query(trimmed, normalized):
        _record(session, lambda: _count_unmatched(session, today, normalized))
