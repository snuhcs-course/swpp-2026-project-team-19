"""separate bar-local menu entries from the shared whisky catalog

Revision ID: c2a6f490b213
Revises: bec46a7503af
Create Date: 2026-11-13

No old product/category rows are deleted or silently reclassified.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c2a6f490b213"
down_revision: Union[str, None] = "bec46a7503af"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bar_local_menu_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("bar_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bars.id"), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("sold_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bar_local_menu_items_bar_id", "bar_local_menu_items", ["bar_id"])


def downgrade() -> None:
    op.drop_index("ix_bar_local_menu_items_bar_id", table_name="bar_local_menu_items")
    op.drop_table("bar_local_menu_items")
