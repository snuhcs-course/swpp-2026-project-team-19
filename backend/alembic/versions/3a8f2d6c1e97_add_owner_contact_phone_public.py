"""add the applicant's consent to show the contact phone to customers

Revision ID: 3a8f2d6c1e97
Revises: 7d1e4b9a2c63
Create Date: 2026-11-27 12:00:00.000000

API spec 3.9, 3.11.2; schema guide 5.4 (bar_owner_applications).

- contact_phone_public: whether the applicant agreed, when applying, that customers may see
  contact_phone while the bar has no phone of its own. Asked only when applying and not changed later.

contact_phone was collected for the operator to reach the applicant, so applications made before this
consent existed get false and their numbers are never shown. The downgrade drops the column.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3a8f2d6c1e97'
down_revision: Union[str, None] = '7d1e4b9a2c63'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bar_owner_applications",
        sa.Column("contact_phone_public", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("bar_owner_applications", "contact_phone_public")
