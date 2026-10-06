"""Keep the deployment templates in step with the code."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.adapters.storage import S3ImageStorage
from app.api import deps

DEPLOY_DIR = Path(__file__).resolve().parents[1] / "deploy"
LINE = re.compile(r"^[A-Z][A-Z0-9_]*=[^\s#'\"]*$")


def production_env() -> dict[str, str]:
    values = {}
    for line in (DEPLOY_DIR / "env.production.example").read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        # systemd's EnvironmentFile takes everything after "=" literally.
        assert LINE.match(line), f"not a plain KEY=VALUE line: {line!r}"
        key, value = line.split("=", 1)
        values[key] = value
    return values


def test_production_env_template_is_plain_key_value():
    values = production_env()

    assert values["IMAGE_STORAGE"] == "s3"
    assert values["POSTGRES_SSLMODE"] == "require"


@pytest.fixture
def clean_caches():
    deps.get_image_storage.cache_clear()
    deps.get_menu_extractor.cache_clear()
    yield
    deps.get_image_storage.cache_clear()
    deps.get_menu_extractor.cache_clear()


def test_the_app_starts_with_the_production_settings(monkeypatch, clean_caches):
    from app.main import app

    for key, value in production_env().items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("TEMP_AUTH_JWT_SECRET", "x" * 64)

    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
    storage = deps.get_image_storage()
    assert isinstance(storage, S3ImageStorage)
    assert storage.bucket == "bottlemap-menu-photos"


def test_deploy_script_finds_uv_without_a_login_shell():
    script = (DEPLOY_DIR / "deploy.sh").read_text()

    # Automatic deployment runs the script over SSH, where ~/.local/bin is not on PATH.
    assert script.index('export PATH="$HOME/.local/bin:$PATH"') < script.index("uv sync")
