# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #9). Reviewed by Haeul Yang.
"""create menu board tables

Revision ID: c1c6275f0b54
Revises: 42821844ea02
Create Date: 2026-10-06 02:59:17.152968
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c1c6275f0b54'
down_revision: Union[str, None] = '42821844ea02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bar_menu_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bar_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["bar_id"], ["bars.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "bar_id", "product_id", name="uq_bar_menu_items_bar_id_product_id"
        ),
    )
    op.create_index("ix_bar_menu_items_product_id", "bar_menu_items", ["product_id"])

    # last_import_id gets its FK to menu_imports.id when that table is created.
    op.create_table(
        "menu_boards",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bar_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_import_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["bar_id"], ["bars.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bar_id"),
    )

    op.create_table(
        "menu_board_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("menu_board_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bar_menu_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["menu_board_id"], ["menu_boards.id"]),
        sa.ForeignKeyConstraint(["bar_menu_item_id"], ["bar_menu_items.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "menu_board_id",
            "sort_order",
            name="uq_menu_board_entries_menu_board_id_sort_order",
        ),
        sa.UniqueConstraint(
            "menu_board_id",
            "bar_menu_item_id",
            name="uq_menu_board_entries_menu_board_id_bar_menu_item_id",
        ),
    )

    # source_extracted_option_id gets its FK to extracted_options.id when that table is created.
    op.create_table(
        "menu_entry_options",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("menu_board_entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "source_extracted_option_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column("option_label", sa.String(length=100), nullable=True),
        sa.Column("pour_ml", sa.SmallInteger(), nullable=True),
        sa.Column("price_krw", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["menu_board_entry_id"], ["menu_board_entries.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "menu_board_entry_id",
            "sort_order",
            name="uq_menu_entry_options_menu_board_entry_id_sort_order",
        ),
    )
    op.create_index("ix_menu_entry_options_price_krw", "menu_entry_options", ["price_krw"])


def downgrade() -> None:
    op.drop_table("menu_entry_options")
    op.drop_table("menu_board_entries")
    op.drop_table("menu_boards")
    op.drop_table("bar_menu_items")
