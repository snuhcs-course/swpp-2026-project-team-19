"""add the cover photo of new_bar owner applications

Revision ID: 9c2e7a4b1d38
Revises: 5f576b601881
Create Date: 2026-11-03 23:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9c2e7a4b1d38'
down_revision: Union[str, None] = '5f576b601881'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable, so existing applications have no cover photo and pass both checks.
    op.add_column("bar_owner_applications", sa.Column("cover_photo_storage_key", sa.String(length=500), nullable=True))
    op.add_column(
        "bar_owner_applications", sa.Column("cover_photo_thumbnail_storage_key", sa.String(length=500), nullable=True)
    )
    op.add_column("bar_owner_applications", sa.Column("cover_photo_sha256", sa.CHAR(length=64), nullable=True))
    op.create_check_constraint(
        "ck_bar_owner_applications_cover_photo_complete",
        "bar_owner_applications",
        "(cover_photo_storage_key IS NULL) = (cover_photo_thumbnail_storage_key IS NULL)"
        " AND (cover_photo_storage_key IS NULL) = (cover_photo_sha256 IS NULL)",
    )
    op.create_check_constraint(
        "ck_bar_owner_applications_cover_photo_pending_new_bar",
        "bar_owner_applications",
        "cover_photo_storage_key IS NULL OR (application_type = 'new_bar' AND status = 'pending')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_bar_owner_applications_cover_photo_pending_new_bar", "bar_owner_applications", type_="check")
    op.drop_constraint("ck_bar_owner_applications_cover_photo_complete", "bar_owner_applications", type_="check")
    op.drop_column("bar_owner_applications", "cover_photo_sha256")
    op.drop_column("bar_owner_applications", "cover_photo_thumbnail_storage_key")
    op.drop_column("bar_owner_applications", "cover_photo_storage_key")
