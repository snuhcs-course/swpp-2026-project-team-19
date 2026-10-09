# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #11). Reviewed by Haeul Yang.
"""create menu import tables

Revision ID: 90a7dfdab17f
Revises: c1c6275f0b54
Create Date: 2026-10-06 11:15:15.695281
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '90a7dfdab17f'
down_revision: Union[str, None] = 'c1c6275f0b54'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ENUMS = {
    "import_status": ("uploaded", "processing", "ready_for_review", "applied", "failed"),
    "import_mode": ("full_replace", "partial_update"),
    "pipeline_status": ("queued", "running", "succeeded", "failed"),
    "extraction_approach": ("ocr_llm", "vision_llm"),
    "extracted_line_type": ("product", "section_header", "description", "unknown"),
    "resolution_status": ("exact_match", "ambiguous", "unmatched"),
    "review_status": ("pending", "confirmed", "corrected", "rejected"),
    "match_method": ("alias", "embedding", "llm", "manual"),
    "menu_change_type": ("add", "update", "remove"),
    "menu_change_decision": ("pending", "apply", "ignore"),
}


def enum(name: str) -> postgresql.ENUM:
    # Types are created once in upgrade(); several columns share some of them.
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def timestamp(name: str, *, nullable: bool = False, default_now: bool = False) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        server_default=sa.text("now()") if default_now else None,
        nullable=nullable,
    )


def uuid(name: str, *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=False)

    op.create_table(
        "menu_imports",
        uuid("id"),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        uuid("bar_id"),
        sa.Column("mode", enum("import_mode"), nullable=False),
        sa.Column("status", enum("import_status"), server_default=sa.text("'uploaded'"), nullable=False),
        sa.Column("review_version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("owner_note", sa.Text(), nullable=True),
        timestamp("review_confirmed_at", nullable=True),
        timestamp("created_at", default_now=True),
        timestamp("completed_at", nullable=True),
        sa.ForeignKeyConstraint(["bar_id"], ["bars.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_menu_imports_bar_id_created_at", "menu_imports", ["bar_id", "created_at"])
    op.create_index("ix_menu_imports_bar_id_status", "menu_imports", ["bar_id", "status"])

    op.create_table(
        "menu_images",
        uuid("id"),
        uuid("menu_import_id"),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("image_order", sa.SmallInteger(), nullable=False),
        timestamp("uploaded_at", default_now=True),
        sa.ForeignKeyConstraint(["menu_import_id"], ["menu_imports.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "menu_import_id", "image_order", name="uq_menu_images_menu_import_id_image_order"
        ),
    )

    op.create_table(
        "extraction_runs",
        uuid("id"),
        uuid("menu_image_id"),
        sa.Column("approach", enum("extraction_approach"), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model_name", sa.String(length=150), nullable=False),
        sa.Column("pipeline_version", sa.String(length=100), nullable=False),
        sa.Column("status", enum("pipeline_status"), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("raw_output", sa.JSON(), nullable=True),
        timestamp("started_at", nullable=True),
        timestamp("completed_at", nullable=True),
        timestamp("created_at", default_now=True),
        sa.ForeignKeyConstraint(["menu_image_id"], ["menu_images.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("menu_image_id"),
    )
    op.create_index(
        "ix_extraction_runs_pipeline_version_status", "extraction_runs", ["pipeline_version", "status"]
    )

    op.create_table(
        "extracted_items",
        uuid("id"),
        uuid("extraction_run_id"),
        sa.Column("item_order", sa.SmallInteger(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column(
            "extracted_line_type",
            enum("extracted_line_type"),
            server_default=sa.text("'unknown'"),
            nullable=False,
        ),
        sa.Column("corrected_line_type", enum("extracted_line_type"), nullable=True),
        sa.Column("extracted_product_name", sa.String(length=200), nullable=True),
        sa.Column("extracted_brand_name", sa.String(length=120), nullable=True),
        sa.Column("extracted_age_years", sa.SmallInteger(), nullable=True),
        sa.Column("extracted_edition_name", sa.String(length=150), nullable=True),
        sa.Column("extracted_abv", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("extraction_confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("initial_resolution_status", enum("resolution_status"), nullable=True),
        uuid("selected_product_id", nullable=True),
        sa.Column("selected_match_method", enum("match_method"), nullable=True),
        sa.Column("match_confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("review_status", enum("review_status"), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("corrected_product_name", sa.String(length=200), nullable=True),
        timestamp("reviewed_at", nullable=True),
        sa.ForeignKeyConstraint(["extraction_run_id"], ["extraction_runs.id"]),
        sa.ForeignKeyConstraint(["selected_product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "extraction_run_id", "item_order", name="uq_extracted_items_extraction_run_id_item_order"
        ),
    )
    op.create_index(
        "ix_extracted_items_extraction_run_id_extracted_line_type",
        "extracted_items",
        ["extraction_run_id", "extracted_line_type"],
    )
    op.create_index(
        "ix_extracted_items_review_status_extraction_confidence",
        "extracted_items",
        ["review_status", "extraction_confidence"],
    )
    op.create_index("ix_extracted_items_selected_product_id", "extracted_items", ["selected_product_id"])

    op.create_table(
        "extracted_options",
        uuid("id"),
        uuid("extracted_item_id"),
        sa.Column("option_order", sa.SmallInteger(), nullable=False),
        sa.Column("extracted_option_label", sa.String(length=100), nullable=True),
        sa.Column("extracted_price_krw", sa.Integer(), nullable=True),
        sa.Column("extracted_pour_ml", sa.SmallInteger(), nullable=True),
        sa.Column("corrected_option_label", sa.String(length=100), nullable=True),
        sa.Column("corrected_price_krw", sa.Integer(), nullable=True),
        sa.Column("corrected_pour_ml", sa.SmallInteger(), nullable=True),
        sa.ForeignKeyConstraint(["extracted_item_id"], ["extracted_items.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "extracted_item_id", "option_order", name="uq_extracted_options_extracted_item_id_option_order"
        ),
    )

    op.create_table(
        "resolution_candidates",
        uuid("id"),
        uuid("extracted_item_id"),
        uuid("product_id"),
        sa.Column("candidate_rank", sa.SmallInteger(), nullable=False),
        sa.Column("score", sa.Numeric(precision=7, scale=6), nullable=True),
        sa.Column("method", enum("match_method"), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=True),
        timestamp("created_at", default_now=True),
        sa.ForeignKeyConstraint(["extracted_item_id"], ["extracted_items.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "extracted_item_id", "candidate_rank", name="uq_resolution_candidates_extracted_item_id_candidate_rank"
        ),
        sa.UniqueConstraint(
            "extracted_item_id", "product_id", name="uq_resolution_candidates_extracted_item_id_product_id"
        ),
    )

    op.create_table(
        "menu_import_changes",
        uuid("id"),
        uuid("menu_import_id"),
        sa.Column("change_type", enum("menu_change_type"), nullable=False),
        uuid("bar_menu_item_id", nullable=True),
        uuid("extracted_item_id", nullable=True),
        sa.Column(
            "decision", enum("menu_change_decision"), server_default=sa.text("'pending'"), nullable=False
        ),
        timestamp("reviewed_at", nullable=True),
        sa.ForeignKeyConstraint(["menu_import_id"], ["menu_imports.id"]),
        sa.ForeignKeyConstraint(["bar_menu_item_id"], ["bar_menu_items.id"]),
        sa.ForeignKeyConstraint(["extracted_item_id"], ["extracted_items.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_menu_import_changes_menu_import_id_change_type", "menu_import_changes", ["menu_import_id", "change_type"]
    )
    op.create_index(
        "ix_menu_import_changes_menu_import_id_decision", "menu_import_changes", ["menu_import_id", "decision"]
    )

    # Columns created earlier without their FK because these tables did not exist yet.
    op.create_foreign_key(
        "products_created_from_extracted_item_id_fkey",
        "products",
        "extracted_items",
        ["created_from_extracted_item_id"],
        ["id"],
    )
    op.create_foreign_key(
        "menu_boards_last_import_id_fkey", "menu_boards", "menu_imports", ["last_import_id"], ["id"]
    )
    op.create_foreign_key(
        "menu_entry_options_source_extracted_option_id_fkey",
        "menu_entry_options",
        "extracted_options",
        ["source_extracted_option_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("menu_entry_options_source_extracted_option_id_fkey", "menu_entry_options", type_="foreignkey")
    op.drop_constraint("menu_boards_last_import_id_fkey", "menu_boards", type_="foreignkey")
    op.drop_constraint("products_created_from_extracted_item_id_fkey", "products", type_="foreignkey")
    for table in (
        "menu_import_changes",
        "resolution_candidates",
        "extracted_options",
        "extracted_items",
        "extraction_runs",
        "menu_images",
        "menu_imports",
    ):
        op.drop_table(table)
    bind = op.get_bind()
    for name in ENUMS:
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
