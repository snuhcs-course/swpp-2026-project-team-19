from decimal import Decimal
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import func, select, text

from app.models import Bar

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_schema_is_at_alembic_head(db_session):
    head = ScriptDirectory.from_config(Config(str(BACKEND_DIR / "alembic.ini"))).get_current_head()

    assert db_session.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == head


def test_committed_rows_are_visible_within_the_test(db_session):
    db_session.add(Bar(name="Test Bar", address="Seoul", latitude=Decimal("37.5"), longitude=Decimal("127.0")))
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(Bar)) == 1


def test_rows_from_the_previous_test_are_rolled_back(db_session):
    assert db_session.scalar(select(func.count()).select_from(Bar)) == 0
