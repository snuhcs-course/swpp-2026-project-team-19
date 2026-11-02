"""add the bar description, default pour, tags, weekly hours and operating exceptions

Revision ID: 6a1d3f9e7c42
Revises: 3e7a9c4d2b15
Create Date: 2026-11-03 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '6a1d3f9e7c42'
down_revision: Union[str, None] = '3e7a9c4d2b15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OPERATING_EXCEPTION_KIND = ("closed_today", "custom_hours", "vacation")


def upgrade() -> None:
    # Existing bars have no description, default pour, tags or hours (spec 3.5).
    op.add_column("bars", sa.Column("description", sa.String(length=100), nullable=True))
    op.add_column("bars", sa.Column("default_pour_ml", sa.SmallInteger(), nullable=True))
    op.add_column(
        "bars",
        sa.Column("tags", postgresql.ARRAY(sa.String(length=24)), server_default=sa.text("'{}'"), nullable=False),
    )
    op.create_check_constraint("ck_bars_default_pour_ml_range", "bars", "default_pour_ml BETWEEN 1 AND 999")
    op.create_check_constraint("ck_bars_tags_count", "bars", "cardinality(tags) <= 5")

    op.create_table(
        "bar_weekly_hours",
        sa.Column("bar_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("day_of_week", sa.SmallInteger(), nullable=False),
        sa.Column("is_closed", sa.Boolean(), nullable=False),
        sa.Column("open_time", sa.Time(), nullable=True),
        sa.Column("close_time", sa.Time(), nullable=True),
        sa.CheckConstraint("day_of_week BETWEEN 1 AND 7", name="ck_bar_weekly_hours_day_of_week"),
        sa.CheckConstraint(
            "(is_closed AND open_time IS NULL AND close_time IS NULL)"
            " OR (NOT is_closed AND open_time IS NOT NULL AND close_time IS NOT NULL AND open_time <> close_time)",
            name="ck_bar_weekly_hours_times",
        ),
        sa.ForeignKeyConstraint(["bar_id"], ["bars.id"]),
        sa.PrimaryKeyConstraint("bar_id", "day_of_week"),
    )

    postgresql.ENUM(*OPERATING_EXCEPTION_KIND, name="operating_exception_kind").create(op.get_bind(), checkfirst=False)
    op.create_table(
        "bar_operating_exceptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bar_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "kind",
            postgresql.ENUM(*OPERATING_EXCEPTION_KIND, name="operating_exception_kind", create_type=False),
            nullable=False,
        ),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("open_time", sa.Time(), nullable=True),
        sa.Column("close_time", sa.Time(), nullable=True),
        sa.Column("note", sa.String(length=100), nullable=True),
        # Null for a temporary-login operator without a users row.
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("end_date >= start_date", name="ck_bar_operating_exceptions_dates"),
        sa.CheckConstraint("kind = 'vacation' OR end_date = start_date", name="ck_bar_operating_exceptions_single_day"),
        sa.CheckConstraint(
            "(kind = 'custom_hours' AND open_time IS NOT NULL AND close_time IS NOT NULL AND open_time <> close_time)"
            " OR (kind <> 'custom_hours' AND open_time IS NULL AND close_time IS NULL)",
            name="ck_bar_operating_exceptions_times",
        ),
        sa.ForeignKeyConstraint(["bar_id"], ["bars.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bar_id"),
    )


def downgrade() -> None:
    op.drop_table("bar_operating_exceptions")
    postgresql.ENUM(name="operating_exception_kind").drop(op.get_bind(), checkfirst=False)
    op.drop_table("bar_weekly_hours")
    op.drop_constraint("ck_bars_tags_count", "bars", type_="check")
    op.drop_constraint("ck_bars_default_pour_ml_range", "bars", type_="check")
    op.drop_column("bars", "tags")
    op.drop_column("bars", "default_pour_ml")
    op.drop_column("bars", "description")
