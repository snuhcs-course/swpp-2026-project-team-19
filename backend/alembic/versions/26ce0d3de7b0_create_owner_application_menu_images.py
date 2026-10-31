"""create owner application menu images

Revision ID: 26ce0d3de7b0
Revises: f9c1f2752a77
Create Date: 2026-10-31 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '26ce0d3de7b0'
down_revision: Union[str, None] = 'f9c1f2752a77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def uuid(name: str) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=False)


def upgrade() -> None:
    op.create_table(
        "bar_owner_application_menu_images",
        uuid("id"),
        uuid("application_id"),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("image_order", sa.SmallInteger(), nullable=False),
        sa.Column("content_sha256", sa.CHAR(length=64), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["bar_owner_applications.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "application_id", "image_order", name="uq_bar_owner_application_menu_images_image_order"
        ),
    )


def downgrade() -> None:
    op.drop_table("bar_owner_application_menu_images")
