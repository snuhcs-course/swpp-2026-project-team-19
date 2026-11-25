"""Keep the deployment templates in step with the code."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.adapters.storage import S3ImageStorage
from app.api import deps
from tests.crypto_support import TEST_BUSINESS_NUMBER_ENCRYPTION_KEY, TEST_BUSINESS_NUMBER_HMAC_KEY

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
    assert (values["MATCHING_LLM_ENABLED"], values["MATCHING_LLM_MODE"]) == ("false", "m3a")


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
    # The template leaves the keys empty, as they are secrets; the server would not start without them.
    monkeypatch.setenv("BUSINESS_NUMBER_ENCRYPTION_KEYS", TEST_BUSINESS_NUMBER_ENCRYPTION_KEY)
    monkeypatch.setenv("BUSINESS_NUMBER_HMAC_KEY", TEST_BUSINESS_NUMBER_HMAC_KEY)

    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
    storage = deps.get_image_storage()
    assert isinstance(storage, S3ImageStorage)
    assert storage.bucket == "bottlemap-menu-photos"


def test_deploy_script_finds_uv_without_a_login_shell():
    script = (DEPLOY_DIR / "deploy.sh").read_text()

    # Automatic deployment runs the script over SSH, where ~/.local/bin is not on PATH.
    assert script.index('export PATH="$HOME/.local/bin:$PATH"') < script.index("uv sync")


def test_the_template_has_every_setting_the_openrouter_extractor_needs(monkeypatch, clean_caches):
    from app.adapters.openrouter_extraction import OpenRouterMenuExtractor

    values = production_env()
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    # The template keeps the old extractor and leaves the secrets empty; fill in only those.
    assert values["MENU_EXTRACTOR"] == "mock"
    for key in ("OPENROUTER_API_KEY", "GEMINI_API_KEY", "CLOVA_OCR_SECRET"):
        assert values[key] == ""
        monkeypatch.setenv(key, "test-secret")
    monkeypatch.setenv("CLOVA_OCR_INVOKE_URL", "https://ocr.example.test/custom/v1/1/abc")
    monkeypatch.setenv("MENU_EXTRACTOR", "openrouter")

    extractor = deps.get_menu_extractor()

    assert isinstance(extractor, OpenRouterMenuExtractor)
    assert extractor.route.openrouter.model == "google/gemini-3.8-flash"
    # Only a model that passed the fallback evaluation (ai/runs/2026-11-21_i5_row_pairing/report.md, section 11).
    assert extractor.route.openrouter.fallback_models == ("anthropic/claude-sonnet-5.5",)
    assert (extractor.route.direct.model, extractor.route.lite.model) == ("gemini-3.8-flash", "gemini-3.5-flash-lite")
