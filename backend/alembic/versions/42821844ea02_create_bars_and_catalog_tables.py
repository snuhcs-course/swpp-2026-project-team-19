"""create bars and catalog tables

Revision ID: 42821844ea02
Revises: 722169dd675e
Create Date: 2026-10-06 01:50:18.542947
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '42821844ea02'
down_revision: Union[str, None] = '722169dd675e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bar_status = postgresql.ENUM("active", "inactive", name="bar_status")
    op.create_table(
        "bars",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("address", sa.String(length=500), nullable=False),
        sa.Column("latitude", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("longitude", sa.Numeric(precision=9, scale=6), nullable=False),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column(
            "status",
            bar_status,
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "brands",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_name", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_name"),
    )

    op.create_table(
        "brand_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alias_text", sa.String(length=120), nullable=False),
        sa.Column("normalized_alias", sa.String(length=120), nullable=False),
        sa.Column("language_code", sa.String(length=10), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "brand_id",
            "normalized_alias",
            name="uq_brand_aliases_brand_id_normalized_alias",
        ),
    )
    op.create_index(
        "ix_brand_aliases_normalized_alias", "brand_aliases", ["normalized_alias"]
    )

    # created_from_extracted_item_id gets its FK to extracted_items.id when that table is created.
    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "category",
            sa.String(length=30),
            server_default=sa.text("'whisky'"),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("age_years", sa.SmallInteger(), nullable=True),
        sa.Column("edition_name", sa.String(length=150), nullable=True),
        sa.Column("abv", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column(
            "created_from_extracted_item_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_products_display_name", "products", ["display_name"])
    op.create_index("ix_products_brand_id_age_years", "products", ["brand_id", "age_years"])
    op.create_index(
        "ix_products_brand_id_edition_name", "products", ["brand_id", "edition_name"]
    )

    op.create_table(
        "product_aliases",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alias_text", sa.String(length=200), nullable=False),
        sa.Column("normalized_alias", sa.String(length=200), nullable=False),
        sa.Column("language_code", sa.String(length=10), nullable=True),
        sa.Column(
            "is_searchable",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_id",
            "normalized_alias",
            name="uq_product_aliases_product_id_normalized_alias",
        ),
    )
    op.create_index(
        "ix_product_aliases_normalized_alias", "product_aliases", ["normalized_alias"]
    )


def downgrade() -> None:
    op.drop_table("product_aliases")
    op.drop_table("products")
    op.drop_table("brand_aliases")
    op.drop_table("brands")
    op.drop_table("bars")
    postgresql.ENUM("active", "inactive", name="bar_status").drop(
        op.get_bind(), checkfirst=True
    )
