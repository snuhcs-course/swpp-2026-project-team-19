"""The review draft columns of menu imports (API spec 5.9, migration 7d1e4b9a2c63)."""

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import ImportMode, MenuImport
from tests.conftest import BACKEND_DIR
from tests.factories import make_bar

BEFORE = "5c3e9a1f7d24"


def make_import(db_session):
    menu_import = MenuImport(
        idempotency_key="draft-key",
        request_fingerprint="0" * 64,
        bar_id=make_bar(db_session).id,
        mode=ImportMode.FULL_REPLACE,
    )
    db_session.add(menu_import)
    db_session.flush()
    return menu_import


def test_an_import_starts_without_a_draft(db_session):
    menu_import = make_import(db_session)
    db_session.flush()
    db_session.refresh(menu_import)

    assert (menu_import.review_draft, menu_import.review_draft_version, menu_import.review_draft_saved_at) == (
        None,
        0,
        None,
    )


def test_the_draft_version_is_never_negative(db_session):
    menu_import = make_import(db_session)
    menu_import.review_draft_version = -1

    with pytest.raises(IntegrityError, match="ck_menu_imports_review_draft_version"):
        db_session.flush()


@pytest.fixture
def migrations(monkeypatch):
    monkeypatch.setenv("POSTGRES_DATABASE", os.environ["POSTGRES_TEST_DATABASE"])
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    try:
        yield config
    finally:
        command.upgrade(config, "head")


def test_the_migration_round_trips(db_engine, migrations):
    command.downgrade(migrations, BEFORE)
    with db_engine.connect() as conn:
        columns = set(
            conn.scalars(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'menu_imports'")
            )
        )
    assert "review_draft" not in columns

    command.upgrade(migrations, "head")
    with db_engine.connect() as conn:
        columns = set(
            conn.scalars(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = 'menu_imports'")
            )
        )
    assert {"review_draft", "review_draft_version", "review_draft_saved_at", "review_draft_saved_by_user_id"} <= columns
