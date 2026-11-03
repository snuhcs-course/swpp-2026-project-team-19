"""add menu import recovery count

Revision ID: 1cbabe615111
Revises: 26ce0d3de7b0
Create Date: 2026-11-01 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '1cbabe615111'
down_revision: Union[str, None] = '26ce0d3de7b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing rows get 0 from the server default.
    op.add_column(
        "menu_imports",
        sa.Column("recovery_count", sa.SmallInteger(), server_default=sa.text("0"), nullable=False),
    )
    op.create_check_constraint("ck_menu_imports_recovery_count", "menu_imports", "recovery_count >= 0")


def downgrade() -> None:
    op.drop_constraint("ck_menu_imports_recovery_count", "menu_imports", type_="check")
    op.drop_column("menu_imports", "recovery_count")
