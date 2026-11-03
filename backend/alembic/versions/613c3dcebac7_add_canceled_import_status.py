"""add canceled import status

Revision ID: 613c3dcebac7
Revises: 1cbabe615111
Create Date: 2026-11-01 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = '613c3dcebac7'
down_revision: Union[str, None] = '1cbabe615111'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_VALUES = ("uploaded", "processing", "ready_for_review", "applied", "failed")


def upgrade() -> None:
    # Allowed in a transaction since PostgreSQL 12; the value is not used in this migration.
    op.execute("ALTER TYPE import_status ADD VALUE 'canceled'")


def downgrade() -> None:
    # PostgreSQL cannot drop an enum value, so the type is created again without it. Canceled
    # imports become failed: both are final, and neither changed the menu.
    op.execute("UPDATE menu_imports SET status = 'failed' WHERE status = 'canceled'")
    op.execute("ALTER TYPE import_status RENAME TO import_status_old")
    op.execute(f"CREATE TYPE import_status AS ENUM ({', '.join(repr(value) for value in OLD_VALUES)})")
    op.execute("ALTER TABLE menu_imports ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE menu_imports ALTER COLUMN status TYPE import_status USING status::text::import_status"
    )
    op.execute("ALTER TABLE menu_imports ALTER COLUMN status SET DEFAULT 'uploaded'")
    op.execute("DROP TYPE import_status_old")
