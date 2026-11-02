"""Bars, their regular opening hours and their temporary closures (API spec 3.6, 3.7, 3.15).

The tables follow docs/schema_draft.dbml; the CHECK constraints are the rules of
docs/schema_guide.md 5.2, 5.6 and 5.7.
"""

from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SQLAlchemyEnum,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    Time,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.db.base import Base


class BarStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class Bar(Base):
    __tablename__ = "bars"
    __table_args__ = (
        CheckConstraint("latitude BETWEEN -90 AND 90", name="ck_bars_latitude_range"),
        CheckConstraint("longitude BETWEEN -180 AND 180", name="ck_bars_longitude_range"),
        CheckConstraint("default_pour_ml BETWEEN 1 AND 999", name="ck_bars_default_pour_ml_range"),
        CheckConstraint("cardinality(tags) <= 5", name="ck_bars_tags_count"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    description: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Only pre-fills glass-option inputs in the app; never applied to stored menu options.
    default_pour_ml: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    # In display order; the API checks the per-tag rules (spec 3.7).
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String(24)), nullable=False, default=list, server_default=text("'{}'")
    )
    status: Mapped[BarStatus] = mapped_column(
        SQLAlchemyEnum(
            BarStatus,
            name="bar_status",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
        default=BarStatus.ACTIVE,
        server_default=text("'active'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class OperatingExceptionKind(str, Enum):
    CLOSED_TODAY = "closed_today"
    CUSTOM_HOURS = "custom_hours"
    VACATION = "vacation"


class BarWeeklyHours(Base):
    """A bar's regular hours on one weekday (ISO 1 = Monday). A weekday without a row has no information,
    which differs from a day off. Times are Seoul local; a close earlier than the open ends the next day."""

    __tablename__ = "bar_weekly_hours"
    __table_args__ = (
        CheckConstraint("day_of_week BETWEEN 1 AND 7", name="ck_bar_weekly_hours_day_of_week"),
        CheckConstraint(
            "(is_closed AND open_time IS NULL AND close_time IS NULL)"
            " OR (NOT is_closed AND open_time IS NOT NULL AND close_time IS NOT NULL AND open_time <> close_time)",
            name="ck_bar_weekly_hours_times",
        ),
    )

    bar_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("bars.id"), primary_key=True)
    day_of_week: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    open_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    close_time: Mapped[time | None] = mapped_column(Time, nullable=True)


class BarOperatingException(Base):
    """A temporary closure or a change to today's hours, at most one per bar. Dates are Seoul local.
    An ended row is not deleted by a job; the API hides it from the second day after `end_date`."""

    __tablename__ = "bar_operating_exceptions"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_bar_operating_exceptions_dates"),
        CheckConstraint(
            "kind = 'vacation' OR end_date = start_date", name="ck_bar_operating_exceptions_single_day"
        ),
        CheckConstraint(
            "(kind = 'custom_hours' AND open_time IS NOT NULL AND close_time IS NOT NULL AND open_time <> close_time)"
            " OR (kind <> 'custom_hours' AND open_time IS NULL AND close_time IS NULL)",
            name="ck_bar_operating_exceptions_times",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    bar_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("bars.id"), nullable=False, unique=True)
    kind: Mapped[OperatingExceptionKind] = mapped_column(
        SQLAlchemyEnum(
            OperatingExceptionKind,
            name="operating_exception_kind",
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    open_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    close_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    note: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Null for a temporary-login operator without a users row.
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
