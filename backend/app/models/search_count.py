"""Daily customer search counts (API spec 3.10.6, schema guide 7.5 and 7.6).

One row per key and Seoul date, never one per search: no query text, time of day, location, user,
IP, device or token is stored.
"""

from datetime import date
from enum import Enum
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, Enum as SQLAlchemyEnum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


class SearchSource(str, Enum):
    """Where a customer search started (API spec 3.10 `source`)."""

    INPUT = "input"
    RECENT = "recent"
    POPULAR = "popular"


class ProductSearchCount(Base):
    """Searches that resolved to exactly one product, per Seoul date, product and source. Ranks the
    popular whiskies (API spec 3.17). Rows older than 90 days are deleted."""

    __tablename__ = "product_search_counts"
    __table_args__ = (CheckConstraint("search_count >= 1", name="ck_product_search_counts_search_count"),)

    search_date: Mapped[date] = mapped_column(Date, primary_key=True)
    # No foreign key, so the counts survive catalogue changes.
    product_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    source: Mapped[SearchSource] = mapped_column(
        SQLAlchemyEnum(
            SearchSource, name="search_source", values_callable=lambda enum: [member.value for member in enum]
        ),
        primary_key=True,
    )
    search_count: Mapped[int] = mapped_column(Integer, nullable=False)


class UnmatchedSearchQuery(Base):
    """Query searches that matched no product, per Seoul date and normalized query, to find what the
    catalogue is missing. No read API; rows older than 30 days are deleted."""

    __tablename__ = "unmatched_search_queries"
    __table_args__ = (CheckConstraint("search_count >= 1", name="ck_unmatched_search_queries_search_count"),)

    search_date: Mapped[date] = mapped_column(Date, primary_key=True)
    # After app.core.normalize.normalize(); the raw input is not kept.
    normalized_query: Mapped[str] = mapped_column(String(200), primary_key=True)
    search_count: Mapped[int] = mapped_column(Integer, nullable=False)
