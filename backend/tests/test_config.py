import pytest

from app.core.config import get_database_url


@pytest.fixture
def database_env(monkeypatch):
    for name, value in {
        "POSTGRES_HOST": "db.example.com",
        "POSTGRES_USER": "bottlemap",
        "POSTGRES_PASSWORD": "p@ss word",
        "POSTGRES_DATABASE": "bottlemap",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("POSTGRES_PORT", raising=False)
    monkeypatch.delenv("POSTGRES_SSLMODE", raising=False)
    return monkeypatch


def test_url_without_ssl_mode_uses_the_driver_default(database_env):
    url = get_database_url()

    assert (url.host, url.port, url.database, url.query) == ("db.example.com", 5432, "bottlemap", {})


def test_ssl_mode_is_passed_to_the_driver(database_env):
    database_env.setenv("POSTGRES_SSLMODE", "require")

    url = get_database_url()

    assert url.query == {"sslmode": "require"}
    # Alembic uses the rendered string; the password stays escaped and the mode is kept.
    assert url.render_as_string(hide_password=False).endswith("@db.example.com:5432/bottlemap?sslmode=require")


def test_invalid_ssl_mode_is_rejected(database_env):
    database_env.setenv("POSTGRES_SSLMODE", "on")

    with pytest.raises(RuntimeError, match="POSTGRES_SSLMODE"):
        get_database_url()


def test_missing_settings_are_named(database_env):
    database_env.delenv("POSTGRES_HOST")

    with pytest.raises(RuntimeError, match="POSTGRES_HOST"):
        get_database_url()
