"""GeminiMenuExtractor and MENU_EXTRACTOR=gemini. extract_menu is always a fake; no test calls the real API."""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app import extraction
from app.adapters.extraction import ExtractionError
from app.adapters.gemini_extraction import GeminiMenuExtractor
from app.api import deps
from app.extraction import gemini
from app.models import ExtractionApproach, LineType

SETTINGS = extraction.ExtractionSettings(
    api_key="secret-test-key", model="gemini-3.5-flash-lite", thinking_level="medium"
)
EXTRACTION_ENV = (
    "GEMINI_API_KEY",
    "EXTRACTION_MODEL",
    "EXTRACTION_THINKING_LEVEL",
    "EXTRACTION_MAX_ATTEMPTS",
    "EXTRACTION_REQUEST_TIMEOUT_S",
    "EXTRACTION_WALL_TIMEOUT_S",
)

META = {
    "model": "gemini-3.5-flash-lite",
    "thinkingLevel": "medium",
    "promptVersion": "v1",
    "latencyMs": 4210,
    "attempts": 2,
    "status": "completed",
    "inputTokens": 3100,
    "outputTokens": 420,
    "thoughtTokens": 900,
    "totalTokens": 4420,
    "rawOutput": {
        "items": [
            {"raw_name": "글렌피딕 12년", "price_krw": 15000, "pour_ml": None, "unit": "glass"},
            {"raw_name": "글렌피딕 12년", "price_krw": 150000, "pour_ml": None, "unit": "bottle"},
        ]
    },
}
ITEMS = [
    {
        "itemOrder": 1,
        "rawText": "글렌피딕 12년",
        "lineType": "product",
        "productName": "글렌피딕 12년",
        "brandText": None,
        "ageYears": None,
        "editionName": None,
        "abv": None,
        "options": [
            {"optionLabel": "잔", "pourMl": None, "priceKrw": 15000},
            {"optionLabel": "병", "pourMl": None, "priceKrw": 150000},
        ],
        "confidence": None,
    }
]


@pytest.fixture(autouse=True)
def no_real_api(monkeypatch):
    def refuse(settings):
        raise AssertionError("tests must not create a real Gemini client")

    monkeypatch.setattr(gemini, "make_client", refuse)


@pytest.fixture
def fake_extract(monkeypatch):
    """Replace extract_menu; set `.result` or `.error` and read `.calls`."""

    class Fake:
        result = {"items": ITEMS, "meta": META}
        error: Exception | None = None
        calls: list = []

        def __call__(self, image, mime_type, *, settings=None, client=None):
            self.calls.append((image, mime_type, settings))
            if self.error is not None:
                raise self.error
            return self.result

    fake = Fake()
    fake.calls = []
    monkeypatch.setattr(extraction, "extract_menu", fake)
    return fake


@pytest.fixture
def env(monkeypatch):
    for name in (*EXTRACTION_ENV, "MENU_EXTRACTOR"):
        monkeypatch.delenv(name, raising=False)
    deps.get_menu_extractor.cache_clear()
    yield monkeypatch
    deps.get_menu_extractor.cache_clear()


def set_gemini_env(env):
    env.setenv("MENU_EXTRACTOR", "gemini")
    env.setenv("GEMINI_API_KEY", "secret-test-key")
    env.setenv("EXTRACTION_MODEL", "gemini-3.5-flash-lite")
    env.setenv("EXTRACTION_THINKING_LEVEL", "medium")


# ---- conversion ----


def test_records_what_produced_the_result():
    extractor = GeminiMenuExtractor(SETTINGS)

    assert extractor.approach == ExtractionApproach.VISION_LLM
    assert (extractor.provider, extractor.model_name) == ("google", "gemini-3.5-flash-lite")
    assert extractor.pipeline_version == "bottlemap-menu-gemini-promptv1-thinking-medium"


def test_converts_items_and_keeps_meta_as_raw_output(fake_extract):
    result = GeminiMenuExtractor(SETTINGS).extract(b"jpeg-bytes", "image/jpeg", "menu.jpg")

    assert fake_extract.calls == [(b"jpeg-bytes", "image/jpeg", SETTINGS)]
    [item] = result.items
    assert (item.item_order, item.raw_text, item.line_type, item.product_name) == (
        1,
        "글렌피딕 12년",
        LineType.PRODUCT,
        "글렌피딕 12년",
    )
    assert (item.brand_text, item.age_years, item.abv, item.confidence) == (None, None, None, None)
    assert [(o.option_label, o.pour_ml, o.price_krw) for o in item.options] == [
        ("잔", None, 15000),
        ("병", None, 150000),
    ]
    # The whole meta: original v1 output, model, tokens, latency, attempts.
    assert result.raw_output == META


def test_filename_does_not_change_the_result(fake_extract):
    extractor = GeminiMenuExtractor(SETTINGS)

    assert extractor.extract(b"x", "image/png", "fail.png") == extractor.extract(b"x", "image/png", None)


def test_menu_without_items(fake_extract):
    fake_extract.result = {"items": [], "meta": {**META, "rawOutput": {"items": []}}}

    result = GeminiMenuExtractor(SETTINGS).extract(b"x", "image/jpeg", None)

    assert (result.items, result.raw_output["rawOutput"]) == ([], {"items": []})


def test_abv_and_confidence_become_decimals(fake_extract):
    fake_extract.result = {"items": [{**ITEMS[0], "abv": 40.0, "confidence": 0.9}], "meta": META}

    [item] = GeminiMenuExtractor(SETTINGS).extract(b"x", "image/jpeg", None).items

    assert (item.abv, item.confidence) == (Decimal("40.00"), Decimal("0.9000"))


# ---- exceptions ----


def test_invalid_model_output_keeps_raw_text_and_meta(fake_extract):
    meta = {**META, "rawOutput": None}
    fake_extract.error = extraction.InvalidModelOutputError("response is not valid v1 output", raw_text="{oops", meta=meta)

    with pytest.raises(ExtractionError) as caught:
        GeminiMenuExtractor(SETTINGS).extract(b"x", "image/jpeg", None)

    assert str(caught.value) == "InvalidModelOutputError: response is not valid v1 output"
    assert caught.value.raw_output == {**meta, "rawText": "{oops"}
    assert isinstance(caught.value.__cause__, extraction.InvalidModelOutputError)


def test_invalid_model_output_without_text(fake_extract):
    fake_extract.error = extraction.InvalidModelOutputError("interaction status is 'failed'", raw_text=None, meta=META)

    with pytest.raises(ExtractionError) as caught:
        GeminiMenuExtractor(SETTINGS).extract(b"x", "image/jpeg", None)

    assert caught.value.raw_output == {**META, "rawText": None}


def test_model_call_error_keeps_attempts(fake_extract):
    fake_extract.error = extraction.ModelCallError("gave up after 6 attempts; last error HardTimeout: ...", attempts=6)

    with pytest.raises(ExtractionError) as caught:
        GeminiMenuExtractor(SETTINGS).extract(b"x", "image/jpeg", None)

    assert str(caught.value).startswith("ModelCallError: gave up after 6 attempts")
    assert caught.value.raw_output == {"attempts": 6}


@pytest.mark.parametrize(
    "error",
    [
        extraction.UnsupportedImageError("Image data is PNG, but MIME type is image/jpeg"),
        extraction.ExtractionConfigError("Missing required extraction environment variables: GEMINI_API_KEY"),
    ],
)
def test_errors_without_model_output(fake_extract, error):
    fake_extract.error = error

    with pytest.raises(ExtractionError) as caught:
        GeminiMenuExtractor(SETTINGS).extract(b"x", "image/jpeg", None)

    assert str(caught.value) == f"{type(error).__name__}: {error}"
    assert caught.value.raw_output is None


def test_items_rejected_by_the_adapter_keep_meta(fake_extract):
    fake_extract.result = {"items": [{**ITEMS[0], "lineType": "drink"}], "meta": META}

    with pytest.raises(ExtractionError) as caught:
        GeminiMenuExtractor(SETTINGS).extract(b"x", "image/jpeg", None)

    assert "lineType" in str(caught.value)
    assert caught.value.raw_output == META


def test_real_extract_menu_errors_are_converted(monkeypatch):
    """Without the fake: a bad image fails inside the real extract_menu before any API call."""
    with pytest.raises(ExtractionError, match="^UnsupportedImageError: "):
        GeminiMenuExtractor(SETTINGS).extract(b"not an image", "image/jpeg", None)


# ---- deps and start-up ----


def test_mock_is_still_the_default(env):
    from app.adapters.extraction import MockMenuExtractor

    assert isinstance(deps.get_menu_extractor(), MockMenuExtractor)


def test_gemini_is_selected(env):
    set_gemini_env(env)
    env.setenv("EXTRACTION_MAX_ATTEMPTS", "3")

    extractor = deps.get_menu_extractor()

    assert isinstance(extractor, GeminiMenuExtractor)
    assert (extractor.model_name, extractor.settings.thinking_level, extractor.settings.max_attempts) == (
        "gemini-3.5-flash-lite",
        "medium",
        3,
    )


@pytest.mark.parametrize("missing", ["GEMINI_API_KEY", "EXTRACTION_MODEL", "EXTRACTION_THINKING_LEVEL"])
def test_missing_setting_is_named(env, missing):
    set_gemini_env(env)
    env.delenv(missing)

    with pytest.raises(RuntimeError, match=f"MENU_EXTRACTOR=gemini is not configured: .*{missing}"):
        deps.get_menu_extractor()


def test_invalid_setting_is_rejected_without_leaking_the_key(env):
    set_gemini_env(env)
    env.setenv("EXTRACTION_THINKING_LEVEL", "extreme")

    with pytest.raises(RuntimeError, match="EXTRACTION_THINKING_LEVEL") as caught:
        deps.get_menu_extractor()

    assert "secret-test-key" not in str(caught.value)


def test_unsupported_extractor_lists_the_choices(env):
    env.setenv("MENU_EXTRACTOR", "openai")

    with pytest.raises(RuntimeError, match=r"supported: mock, gemini"):
        deps.get_menu_extractor()


def test_server_start_fails_when_gemini_is_not_configured(env):
    from app.main import app

    env.setenv("MENU_EXTRACTOR", "gemini")

    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        with TestClient(app):
            pass


def test_server_starts_with_the_mock(env):
    from app.main import app

    with TestClient(app) as client:
        assert client.get("/openapi.json").status_code == 200
