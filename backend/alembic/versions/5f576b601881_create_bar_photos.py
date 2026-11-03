"""create bar_photos for the bar gallery photos

Revision ID: 5f576b601881
Revises: 6a1d3f9e7c42
Create Date: 2026-11-03 21:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '5f576b601881'
down_revision: Union[str, None] = '6a1d3f9e7c42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bar_photos",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bar_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("thumbnail_storage_key", sa.String(length=500), nullable=False),
        # Of the uploaded bytes before re-encoding.
        sa.Column("content_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False),
        # Null for a temporary-login operator without a users row.
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["bar_id"], ["bars.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bar_id", "content_sha256", name="uq_bar_photos_content_sha256"),
        # Checked at commit, so a reorder can swap positions in one transaction. Its index also finds
        # each bar's cover photo (sort_order 1) for the bar list APIs.
        sa.UniqueConstraint(
            "bar_id", "sort_order", name="uq_bar_photos_sort_order", deferrable=True, initially="DEFERRED"
        ),
    )


def downgrade() -> None:
    op.drop_table("bar_photos")
