"""add menu board version, option discounts, and catalog creators

Revision ID: 5d2e8b71c4a9
Revises: 613c3dcebac7
Create Date: 2026-11-02 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '5d2e8b71c4a9'
down_revision: Union[str, None] = '613c3dcebac7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing boards start at version 1 from the server default.
    op.add_column(
        "menu_boards",
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
    )
    op.create_check_constraint("ck_menu_boards_version", "menu_boards", "version >= 1")

    # Existing options have no discount, so the checks hold for every current row.
    op.add_column("menu_entry_options", sa.Column("discount_price_krw", sa.Integer(), nullable=True))
    op.add_column("menu_entry_options", sa.Column("discount_starts_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("menu_entry_options", sa.Column("discount_ends_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_menu_entry_options_discount_complete",
        "menu_entry_options",
        "(discount_price_krw IS NULL) = (discount_starts_at IS NULL) "
        "AND (discount_starts_at IS NULL) = (discount_ends_at IS NULL)",
    )
    op.create_check_constraint(
        "ck_menu_entry_options_discount_price",
        "menu_entry_options",
        "discount_price_krw BETWEEN 1 AND price_krw - 1",
    )
    op.create_check_constraint(
        "ck_menu_entry_options_discount_period",
        "menu_entry_options",
        "discount_ends_at > discount_starts_at",
    )

    # Null for seeded rows and for rows created by a temporary-login operator without a users row.
    for table in ("brands", "products"):
        op.add_column(
            table,
            sa.Column(
                "created_by_user_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("users.id"),
                nullable=True,
            ),
        )


def downgrade() -> None:
    for table in ("products", "brands"):
        op.drop_column(table, "created_by_user_id")

    op.drop_constraint("ck_menu_entry_options_discount_period", "menu_entry_options", type_="check")
    op.drop_constraint("ck_menu_entry_options_discount_price", "menu_entry_options", type_="check")
    op.drop_constraint("ck_menu_entry_options_discount_complete", "menu_entry_options", type_="check")
    op.drop_column("menu_entry_options", "discount_ends_at")
    op.drop_column("menu_entry_options", "discount_starts_at")
    op.drop_column("menu_entry_options", "discount_price_krw")

    op.drop_constraint("ck_menu_boards_version", "menu_boards", type_="check")
    op.drop_column("menu_boards", "version")
