# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #9, #11, #12, #16). Reviewed by Haeul Yang.
"""Shared fixtures for tests that need PostgreSQL.

Tests that use `db_session` or `client` run against the database named by
POSTGRES_TEST_DATABASE (same host and credentials as the app). When it is not set,
those tests are skipped and the rest still run:

    uv run --env-file .env pytest

The schema is rebuilt from the Alembic migrations once per test run, and every test
runs inside a transaction that is rolled back afterwards.
"""

import os
from collections.abc import Iterator
from contextlib import nullcontext
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def mock_extractor(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Use the mock extractor even when .env selects gemini, so no test calls the real API.

    Tests that need other settings set them on top of this.
    """
    from app.api.deps import get_menu_extractor

    monkeypatch.setenv("MENU_EXTRACTOR", "mock")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    get_menu_extractor.cache_clear()
    yield
    get_menu_extractor.cache_clear()


@pytest.fixture(scope="session")
def db_engine() -> Iterator[Engine]:
    test_database = os.getenv("POSTGRES_TEST_DATABASE")
    if not test_database:
        pytest.skip("POSTGRES_TEST_DATABASE is not set")
    # The schema is dropped below, so never point this at a development database.
    if not test_database.endswith("_test"):
        pytest.exit(f"POSTGRES_TEST_DATABASE must end with '_test', got {test_database!r}", returncode=1)

    # Alembic's env.py and get_database_url() read POSTGRES_DATABASE.
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("POSTGRES_DATABASE", test_database)
        from app.core.config import get_database_url

        engine = create_engine(get_database_url())
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
        command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")

    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    """A session whose changes, including commits made by the code under test, are rolled back."""
    with db_engine.connect() as conn:
        transaction = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


TEST_JWT_SECRET = "test-secret-for-temporary-auth-0123456789"


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    """API client whose requests use `db_session`."""
    from app.db.session import get_serializable_session_factory, get_session, get_session_factory
    from app.main import app

    app.dependency_overrides[get_session] = lambda: db_session
    # Background work (run by TestClient right after the response) uses the same session.
    app.dependency_overrides[get_session_factory] = lambda: (lambda: nullcontext(db_session))
    app.dependency_overrides[get_serializable_session_factory] = lambda: (lambda: nullcontext(db_session))
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_session_factory, None)
        app.dependency_overrides.pop(get_serializable_session_factory, None)


@pytest.fixture
def token_for(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    """Issue a temporary-auth access token for a user type: token_for("operator")."""
    monkeypatch.setenv("TEMP_AUTH_ENABLED", "true")
    monkeypatch.setenv("TEMP_AUTH_JWT_SECRET", TEST_JWT_SECRET)

    def issue(user_type: str) -> str:
        monkeypatch.setenv("TEMP_AUTH_USER_TYPE", user_type)
        return client.post("/api/auth/temp-login").json()["accessToken"]

    return issue


@pytest.fixture
def image_storage(tmp_path: Path) -> Iterator["LocalImageStorage"]:
    """Image storage in a temporary directory, used by the API instead of the configured one."""
    from app.adapters.storage import LocalImageStorage
    from app.api.deps import get_image_storage
    from app.main import app

    storage = LocalImageStorage(tmp_path / "images")
    app.dependency_overrides[get_image_storage] = lambda: storage
    try:
        yield storage
    finally:
        app.dependency_overrides.pop(get_image_storage, None)
