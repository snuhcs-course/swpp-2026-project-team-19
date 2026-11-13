"""add unlinked menu items, menu item kinds, and operator menu item checks

Revision ID: 5c3e9a1f7d24
Revises: bec46a7503af
Create Date: 2026-11-13 12:00:00.000000

API spec 2.3, 3.9, 3.18 and 8.10; schema guide 7.1, 7.7, 7.8 and 8.4.

- bar_menu_items: product_id becomes nullable so a bar can publish a whisky the catalog does not have yet
  (kind = whisky, waiting for an operator) or a non-whisky menu (kind = other, never linked). An unlinked
  item is identified within the bar by name_key.
- extracted_items: extracted_kind (the AI's kind) and corrected_kind (the reviewer's, when different).
  Existing product lines were all whisky, the only lines extraction returned so far.
- menu_item_checks and menu_item_check_reasons: the operator's check list.

Existing rows stay valid: every current bar menu item has a product and becomes kind = whisky.

The downgrade restores product_id NOT NULL, which an unlinked item cannot satisfy. It refuses to run while
any bar menu item has no product, instead of deleting menu data; those items have to be linked, or
removed from their boards and deleted, by hand first.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '5c3e9a1f7d24'
down_revision: Union[str, None] = 'bec46a7503af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ENUMS = {
    "menu_item_kind": ("whisky", "other"),
    "menu_item_check_reason": (
        "unlinked",
        "relinked_by_name",
        "unlinked_by_name",
        "attribute_conflict",
        "price_conflict",
    ),
    "menu_item_check_status": ("open", "resolved", "dismissed"),
    "menu_item_check_resolution": ("link_existing", "create_and_link", "keep", "mark_as_other"),
}


def enum(name: str) -> postgresql.ENUM:
    # Types are created once in upgrade().
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind)

    op.alter_column("bar_menu_items", "product_id", existing_type=sa.Uuid(), nullable=True)
    op.add_column(
        "bar_menu_items",
        sa.Column("kind", enum("menu_item_kind"), server_default=sa.text("'whisky'"), nullable=False),
    )
    op.add_column("bar_menu_items", sa.Column("name_key", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_bar_menu_items_name_key_when_unlinked", "bar_menu_items", "(product_id IS NULL) = (name_key IS NOT NULL)"
    )
    op.create_check_constraint(
        "ck_bar_menu_items_other_is_unlinked", "bar_menu_items", "kind = 'whisky' OR product_id IS NULL"
    )
    op.create_index("ix_bar_menu_items_bar_id_name_key", "bar_menu_items", ["bar_id", "name_key"])

    op.add_column("extracted_items", sa.Column("extracted_kind", enum("menu_item_kind"), nullable=True))
    op.add_column("extracted_items", sa.Column("corrected_kind", enum("menu_item_kind"), nullable=True))
    op.execute("UPDATE extracted_items SET extracted_kind = 'whisky' WHERE extracted_line_type = 'product'")

    op.create_table(
        "menu_item_checks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("bar_id", sa.Uuid(), nullable=False),
        sa.Column("bar_menu_item_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("status", enum("menu_item_check_status"), server_default=sa.text("'open'"), nullable=False),
        sa.Column(
            "discarded_options",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("resolution", enum("menu_item_check_resolution"), nullable=True),
        sa.Column("resolved_product_id", sa.Uuid(), nullable=True),
        sa.Column("resolved_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("(status = 'resolved') = (resolution IS NOT NULL)", name="ck_menu_item_checks_resolution"),
        sa.CheckConstraint("(status = 'open') = (resolved_at IS NULL)", name="ck_menu_item_checks_resolved_at"),
        sa.ForeignKeyConstraint(["bar_id"], ["bars.id"]),
        sa.ForeignKeyConstraint(["bar_menu_item_id"], ["bar_menu_items.id"]),
        sa.ForeignKeyConstraint(["resolved_product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_menu_item_checks_open_bar_menu_item_id",
        "menu_item_checks",
        ["bar_menu_item_id"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_index("ix_menu_item_checks_status_created_at", "menu_item_checks", ["status", "created_at"])
    op.create_index("ix_menu_item_checks_bar_id_status", "menu_item_checks", ["bar_id", "status"])

    op.create_table(
        "menu_item_check_reasons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("check_id", sa.Uuid(), nullable=False),
        sa.Column("reason", enum("menu_item_check_reason"), nullable=False),
        sa.Column("source_menu_import_id", sa.Uuid(), nullable=True),
        sa.Column("source_extracted_item_id", sa.Uuid(), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "(source_menu_import_id IS NULL) = (source_extracted_item_id IS NULL)",
            name="ck_menu_item_check_reasons_source_complete",
        ),
        sa.ForeignKeyConstraint(["check_id"], ["menu_item_checks.id"]),
        sa.ForeignKeyConstraint(["source_menu_import_id"], ["menu_imports.id"]),
        sa.ForeignKeyConstraint(["source_extracted_item_id"], ["extracted_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_menu_item_check_reasons_check_id_added_at", "menu_item_check_reasons", ["check_id", "added_at"]
    )


def downgrade() -> None:
    bind = op.get_bind()
    unlinked = bind.execute(sa.text("SELECT count(*) FROM bar_menu_items WHERE product_id IS NULL")).scalar_one()
    if unlinked:
        raise RuntimeError(
            f"{unlinked} bar menu items have no product; link them, or remove them from their boards and "
            "delete them, before downgrading (product_id becomes NOT NULL again)"
        )

    op.drop_table("menu_item_check_reasons")
    op.drop_table("menu_item_checks")
    op.drop_column("extracted_items", "corrected_kind")
    op.drop_column("extracted_items", "extracted_kind")
    op.drop_index("ix_bar_menu_items_bar_id_name_key", table_name="bar_menu_items")
    op.drop_constraint("ck_bar_menu_items_other_is_unlinked", "bar_menu_items", type_="check")
    op.drop_constraint("ck_bar_menu_items_name_key_when_unlinked", "bar_menu_items", type_="check")
    op.drop_column("bar_menu_items", "name_key")
    op.drop_column("bar_menu_items", "kind")
    op.alter_column("bar_menu_items", "product_id", existing_type=sa.Uuid(), nullable=False)
    for name in ENUMS:
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
