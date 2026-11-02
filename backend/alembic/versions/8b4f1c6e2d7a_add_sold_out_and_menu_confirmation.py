"""add sold-out on bar menu items and the sales info confirmation on menu boards

Revision ID: 8b4f1c6e2d7a
Revises: 5d2e8b71c4a9
Create Date: 2026-11-03 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '8b4f1c6e2d7a'
down_revision: Union[str, None] = '5d2e8b71c4a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing items are on sale, and existing boards were never confirmed.
    op.add_column("bar_menu_items", sa.Column("sold_out_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("menu_boards", sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True))
    # Null when never confirmed, or for a temporary-login operator without a users row.
    op.add_column(
        "menu_boards",
        sa.Column("confirmed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("menu_boards", "confirmed_by_user_id")
    op.drop_column("menu_boards", "confirmed_at")
    op.drop_column("bar_menu_items", "sold_out_at")
