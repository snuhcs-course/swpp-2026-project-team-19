# AI-generated with Claude Code/Claude Opus 5.5 (Haeul Yang, 2026-10-18). Reviewed by Haeul Yang.
"""check bar coordinate ranges

Revision ID: a753618f55f5
Revises: 90a7dfdab17f
Create Date: 2026-10-18 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'a753618f55f5'
down_revision: Union[str, None] = '90a7dfdab17f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Fails if an existing bar is out of range; fix that row before upgrading.
    op.create_check_constraint("ck_bars_latitude_range", "bars", "latitude BETWEEN -90 AND 90")
    op.create_check_constraint("ck_bars_longitude_range", "bars", "longitude BETWEEN -180 AND 180")


def downgrade() -> None:
    op.drop_constraint("ck_bars_longitude_range", "bars", type_="check")
    op.drop_constraint("ck_bars_latitude_range", "bars", type_="check")
