"""add review drafts to menu imports

Revision ID: 7d1e4b9a2c63
Revises: 5c3e9a1f7d24
Create Date: 2026-11-14 12:00:00.000000

API spec 5.9; schema guide 8.1 (menu_imports).

- review_draft: the reviewer's unfinished input, saved before submission so the review can go on from
  another device or the operator web. The server does not interpret it. Cleared on apply or cancel.
  json, not jsonb: the text is kept as sent, so any valid JSON is accepted (jsonb refuses U+0000 in a
  string) and the keys come back in their order.
- review_draft_version: raised on every save; a save sends the version it read, so two editors do not
  overwrite each other. Not reset when the draft is cleared.
- review_draft_review_version: the reviewVersion of the review data the draft was entered on, sent back
  with the draft so a client can tell the review data was rebuilt since (spec 5.4).
- review_draft_saved_at, review_draft_saved_by_user_id: who saved it last, and when.

Existing imports get no draft and version 0. The downgrade drops the columns and any saved drafts.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '7d1e4b9a2c63'
down_revision: Union[str, None] = '5c3e9a1f7d24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("menu_imports", sa.Column("review_draft", postgresql.JSON(), nullable=True))
    op.add_column(
        "menu_imports",
        sa.Column("review_draft_version", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("menu_imports", sa.Column("review_draft_review_version", sa.Integer(), nullable=True))
    op.add_column("menu_imports", sa.Column("review_draft_saved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "menu_imports",
        sa.Column(
            "review_draft_saved_by_user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_menu_imports_review_draft_version", "menu_imports", "review_draft_version >= 0"
    )


def downgrade() -> None:
    op.drop_constraint("ck_menu_imports_review_draft_version", "menu_imports", type_="check")
    op.drop_column("menu_imports", "review_draft_saved_by_user_id")
    op.drop_column("menu_imports", "review_draft_saved_at")
    op.drop_column("menu_imports", "review_draft_review_version")
    op.drop_column("menu_imports", "review_draft_version")
    op.drop_column("menu_imports", "review_draft")
