"""create the daily search count tables

Revision ID: 3e7a9c4d2b15
Revises: 8b4f1c6e2d7a
Create Date: 2026-11-03 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '3e7a9c4d2b15'
down_revision: Union[str, None] = '8b4f1c6e2d7a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEARCH_SOURCE = ("input", "recent", "popular")


def upgrade() -> None:
    postgresql.ENUM(*SEARCH_SOURCE, name="search_source").create(op.get_bind(), checkfirst=False)

    # product_id has no foreign key, so the counts survive catalogue changes.
    op.create_table(
        "product_search_counts",
        sa.Column("search_date", sa.Date(), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "source", postgresql.ENUM(*SEARCH_SOURCE, name="search_source", create_type=False), nullable=False
        ),
        sa.Column("search_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("search_count >= 1", name="ck_product_search_counts_search_count"),
        sa.PrimaryKeyConstraint("search_date", "product_id", "source"),
    )
    op.create_table(
        "unmatched_search_queries",
        sa.Column("search_date", sa.Date(), nullable=False),
        sa.Column("normalized_query", sa.String(length=200), nullable=False),
        sa.Column("search_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("search_count >= 1", name="ck_unmatched_search_queries_search_count"),
        sa.PrimaryKeyConstraint("search_date", "normalized_query"),
    )


def downgrade() -> None:
    op.drop_table("unmatched_search_queries")
    op.drop_table("product_search_counts")
    postgresql.ENUM(name="search_source").drop(op.get_bind(), checkfirst=False)
