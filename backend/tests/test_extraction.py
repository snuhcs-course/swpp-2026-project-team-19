"""Menu extraction tests. The Gemini client is always a fake; no test calls the real API."""

import base64
import hashlib
import io
import json
import threading
from types import SimpleNamespace

import pytest
from PIL import Image
from pydantic import ValidationError

from app.extraction import (
    ExtractionConfigError,
    ExtractionSettings,
    InvalidModelOutputError,
    ModelCallError,
    UnsupportedImageError,
    extract_menu,
    load_settings,
)
from app.extraction import gemini
from app.extraction.convert import to_flow_items
from app.extraction.image import prepare_image
from app.extraction.schema import ExtractionItems, MenuExtraction
from app.extraction.service import load_prompt

# P14 prompt v1 (ai/runs/2026-10-04_A2/manifest.json prompt_sha256)
P14_PROMPT_SHA256 = "1b4414e1943b0035921d2abf4380901d084b724f4395d3f3d12f6319c46b9ef8"
# MenuExtraction.model_json_schema() as sent in P14 (google-genai 2.28.0, pydantic 2.13.5)
P14_RESPONSE_SCHEMA = {
    "$defs": {
        "MenuItem": {
            "properties": {
                "raw_name": {"title": "Raw Name", "type": "string"},
                "price_krw": {"anyOf": [{"type": "integer"}, {"type": "null"}], "title": "Price Krw"},
                "pour_ml": {"anyOf": [{"type": "integer"}, {"type": "null"}], "title": "Pour Ml"},
                "unit": {
                    "anyOf": [{"enum": ["glass", "bottle"], "type": "string"}, {"type": "null"}],
                    "title": "Unit",
                },
            },
            "required": ["raw_name", "price_krw", "pour_ml", "unit"],
            "title": "MenuItem",
            "type": "object",
        }
    },
    "properties": {"items": {"items": {"$ref": "#/$defs/MenuItem"}, "title": "Items", "type": "array"}},
    "required": ["items"],
    "title": "MenuExtraction",
    "type": "object",
}

SETTINGS = ExtractionSettings(
    api_key="test-key", model="gemini-3.5-flash-lite", thinking_level="medium", max_attempts=3
)


def png_bytes(size=(4, 2)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, "white").save(out, format="PNG")
    return out.getvalue()


def jpeg_bytes(size=(4, 2), orientation=None) -> bytes:
    out = io.BytesIO()
    exif = Image.Exif()
    if orientation is not None:
        exif[0x0112] = orientation
    Image.new("RGB", size, "white").save(out, format="JPEG", exif=exif.tobytes())
    return out.getvalue()


def v1(name, price, unit, pour=None):
    return {"raw_name": name, "price_krw": price, "pour_ml": pour, "unit": unit}


def interaction(items=None, *, text=None, status="completed"):
    if text is None:
        text = json.dumps({"items": items or []}, ensure_ascii=False)
    usage = SimpleNamespace(
        total_input_tokens=2313, total_output_tokens=1232, total_thought_tokens=1449, total_tokens=4994
    )
    return SimpleNamespace(status=status, output_text=text, usage=usage)


class FakeClient:
    """Stands in for genai.Client; each create() returns or raises the next scripted response."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.interactions = self

    def create(self, **request):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        if callable(response):
            return response()
        return response


class StatusError(Exception):
    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.code = code


@pytest.fixture(autouse=True)
def no_real_api(monkeypatch):
    def refuse(settings):
        raise AssertionError("tests must not create a real Gemini client")

    monkeypatch.setattr(gemini, "make_client", refuse)
    monkeypatch.setattr(gemini, "sleep", lambda seconds: None)


# ---- Parity with the P14 experiment ----


def test_prompt_is_p14_v1():
    assert hashlib.sha256(load_prompt().encode("utf-8")).hexdigest() == P14_PROMPT_SHA256


def test_response_schema_is_p14_v1():
    assert MenuExtraction.model_json_schema() == P14_RESPONSE_SCHEMA


def test_request_matches_p14_call():
    client = FakeClient(interaction([]))
    image = png_bytes()

    extract_menu(image, "image/png", settings=SETTINGS, client=client)

    request = client.requests[0]
    assert request["model"] == "gemini-3.5-flash-lite"
    assert request["generation_config"] == {"thinking_level": "medium"}
    assert request["store"] is False
    assert request["system_instruction"] == load_prompt()
    assert request["response_format"] == {
        "type": "text",
        "mime_type": "application/json",
        "schema": P14_RESPONSE_SCHEMA,
    }
    assert request["input"] == [
        {"type": "text", "text": "이 메뉴판 사진에서 규칙에 따라 항목을 추출해."},
        {"type": "image", "data": base64.b64encode(image).decode("ascii"), "mime_type": "image/png"},
    ]
    assert request["timeout"] == 300
    assert "temperature" not in request and "temperature" not in request["generation_config"]


# ---- extract_menu ----


def test_extract_menu_returns_flow_items_and_meta():
    raw = [
        v1("글렌그란트 18년 / Glen Grant 18Y", 28000, "glass"),
        v1("글렌그란트 18년 / Glen Grant 18Y", 570000, "bottle"),
        v1("글렌알라키 18년 / GlenAllachie 18Y", 39000, "glass"),
    ]
    result = extract_menu(png_bytes(), "image/png", settings=SETTINGS, client=FakeClient(interaction(raw)))

    assert result["items"] == [
        {
            "itemOrder": 1,
            "rawText": "글렌그란트 18년 / Glen Grant 18Y",
            "lineType": "product",
            "productName": "글렌그란트 18년 / Glen Grant 18Y",
            "brandText": None,
            "ageYears": None,
            "editionName": None,
            "abv": None,
            "options": [
                {"optionLabel": "잔", "pourMl": None, "priceKrw": 28000},
                {"optionLabel": "병", "pourMl": None, "priceKrw": 570000},
            ],
            "confidence": None,
        },
        {
            "itemOrder": 2,
            "rawText": "글렌알라키 18년 / GlenAllachie 18Y",
            "lineType": "product",
            "productName": "글렌알라키 18년 / GlenAllachie 18Y",
            "brandText": None,
            "ageYears": None,
            "editionName": None,
            "abv": None,
            "options": [{"optionLabel": "잔", "pourMl": None, "priceKrw": 39000}],
            "confidence": None,
        },
    ]
    meta = result["meta"]
    assert meta["rawOutput"] == {"items": raw}
    assert meta["model"] == "gemini-3.5-flash-lite"
    assert meta["thinkingLevel"] == "medium"
    assert meta["promptVersion"] == "v1"
    assert meta["promptSha256"] == P14_PROMPT_SHA256
    assert meta["sdk"] == "google-genai 2.28.0"
    assert (meta["inputTokens"], meta["outputTokens"], meta["thoughtTokens"]) == (2313, 1232, 1449)
    assert meta["attempts"] == 1
    assert meta["status"] == "completed"
    assert isinstance(meta["latencyMs"], int)
    json.dumps(result)  # P18 stores it as JSON


def test_menu_without_items():
    result = extract_menu(png_bytes(), "image/png", settings=SETTINGS, client=FakeClient(interaction([])))

    assert result["items"] == []
    assert result["meta"]["rawOutput"] == {"items": []}


def test_unparseable_answer_keeps_raw_text_and_meta():
    client = FakeClient(interaction(text="{not json"))

    with pytest.raises(InvalidModelOutputError) as info:
        extract_menu(png_bytes(), "image/png", settings=SETTINGS, client=client)

    assert info.value.raw_text == "{not json"
    assert info.value.meta["inputTokens"] == 2313
    assert info.value.meta["rawOutput"] is None


def test_incomplete_interaction_is_rejected():
    client = FakeClient(interaction([], status="incomplete"))

    with pytest.raises(InvalidModelOutputError, match="incomplete"):
        extract_menu(png_bytes(), "image/png", settings=SETTINGS, client=client)


@pytest.mark.parametrize(
    "item",
    [
        v1("", 10000, "glass"),
        v1("가" * 201, 10000, "glass"),
        v1("발베니 12년", -1000, "glass"),
        v1("발베니 12년", 0, "glass"),
        v1("발베니 12년", 10_000_001, "bottle"),
        v1("발베니 12년", 10000, "glass", pour=0),
        v1("발베니 12년", 10000, "glass", pour=40000),
    ],
    ids=["empty-name", "long-name", "negative-price", "zero-price", "huge-price", "zero-pour", "huge-pour"],
)
def test_out_of_range_values_are_rejected(item):
    client = FakeClient(interaction([item]))

    with pytest.raises(InvalidModelOutputError) as info:
        extract_menu(png_bytes(), "image/png", settings=SETTINGS, client=client)

    assert info.value.meta["rawOutput"] == {"items": [item]}


def test_wrong_unit_value_is_rejected():
    text = json.dumps({"items": [v1("발베니 12년", 10000, "shot")]})

    with pytest.raises(InvalidModelOutputError):
        extract_menu(png_bytes(), "image/png", settings=SETTINGS, client=FakeClient(interaction(text=text)))


# ---- Conversion ----


def test_adjacent_glass_and_bottle_become_one_item_in_either_order():
    items = to_flow_items([v1("A", 570000, "bottle"), v1("A", 28000, "glass")])

    assert len(items) == 1
    assert [o["optionLabel"] for o in items[0]["options"]] == ["병", "잔"]


def test_same_name_elsewhere_on_the_menu_is_not_merged():
    items = to_flow_items([v1("A", 28000, "glass"), v1("B", 30000, "glass"), v1("A", 570000, "bottle")])

    assert [(i["itemOrder"], i["rawText"], len(i["options"])) for i in items] == [
        (1, "A", 1),
        (2, "B", 1),
        (3, "A", 1),
    ]


def test_same_name_and_unit_twice_is_not_merged():
    items = to_flow_items([v1("A", 28000, "glass"), v1("A", 30000, "glass")])

    assert len(items) == 2


def test_a_pair_takes_at_most_two_entries():
    items = to_flow_items([v1("A", 1000, "glass"), v1("A", 2000, "bottle"), v1("A", 3000, "glass")])

    assert [len(i["options"]) for i in items] == [2, 1]


def test_pour_and_missing_values():
    items = to_flow_items([v1("A", 15000, None, pour=30), v1("B", None, None), v1("C", None, "glass")])

    assert items[0]["options"] == [{"optionLabel": None, "pourMl": 30, "priceKrw": 15000}]
    assert items[1]["options"] == []
    assert items[2]["options"] == [{"optionLabel": "잔", "pourMl": None, "priceKrw": None}]
    ExtractionItems.model_validate({"items": items})


# ---- 4.3 validation (also covers line types prompt v1 does not produce yet) ----


def flow_item(**overrides):
    item = {
        "itemOrder": 1,
        "rawText": "딘스톤 12년",
        "lineType": "product",
        "productName": "딘스톤 12년",
        "brandText": "딘스톤",
        "ageYears": 12,
        "editionName": None,
        "abv": 46.3,
        "options": [{"optionLabel": None, "pourMl": 15, "priceKrw": 8000}],
        "confidence": 0.92,
    }
    return item | overrides


def test_valid_flow_items():
    header = flow_item(
        itemOrder=2, rawText="싱글 몰트", lineType="section_header", productName=None,
        brandText=None, ageYears=None, abv=None, options=[], confidence=0.98,
    )
    ExtractionItems.model_validate({"items": [flow_item(), header]})


@pytest.mark.parametrize(
    "overrides",
    [
        {"lineType": "cocktail"},
        {"productName": None},
        {"confidence": 1.5},
        {"ageYears": 0},
        {"abv": 120},
        {"options": [{"optionLabel": None, "pourMl": None, "priceKrw": None}]},
        {"options": [{"optionLabel": "잔", "pourMl": None, "priceKrw": 1}] * 2},
        {"options": [{"optionLabel": "잔", "pourMl": None, "priceKrw": 1, "currency": "KRW"}]},
        {"lineType": "section_header", "productName": None, "brandText": None, "ageYears": None, "abv": None},
        {"lineType": "description", "productName": None, "ageYears": None, "abv": None, "options": []},
        {"itemOrder": 0},
    ],
    ids=[
        "bad-line-type", "product-without-name", "confidence-over-1", "age-0", "abv-over-100",
        "empty-option", "duplicate-option", "extra-option-key", "header-with-options",
        "description-with-product-fields", "order-0",
    ],
)
def test_invalid_flow_items(overrides):
    with pytest.raises(ValidationError):
        ExtractionItems.model_validate({"items": [flow_item(**overrides)]})


def test_item_order_must_be_unique():
    with pytest.raises(ValidationError):
        ExtractionItems.model_validate({"items": [flow_item(), flow_item()]})


# ---- Images ----


def test_png_without_rotation_is_sent_unchanged():
    data = png_bytes()

    assert prepare_image(data, "image/png") == (data, "image/png")


def test_jpeg_without_exif_is_sent_unchanged_and_jpg_alias_is_accepted():
    data = jpeg_bytes()

    assert prepare_image(data, "Image/JPG") == (data, "image/jpeg")


def test_exif_rotated_jpeg_is_rotated_once():
    prepared, mime = prepare_image(jpeg_bytes(size=(4, 2), orientation=6), "image/jpeg")

    assert mime == "image/jpeg"
    with Image.open(io.BytesIO(prepared)) as im:
        assert im.size == (2, 4)
        assert im.getexif().get(0x0112) is None


@pytest.mark.parametrize(
    ("data", "mime"),
    [
        (png_bytes(), "image/webp"),
        (png_bytes(), "image/jpeg"),
        (b"not an image", "image/png"),
        (b"", "image/png"),
    ],
    ids=["unsupported-type", "type-mismatch", "garbage", "empty"],
)
def test_bad_images_are_rejected_before_the_call(data, mime):
    client = FakeClient()

    with pytest.raises(UnsupportedImageError):
        extract_menu(data, mime, settings=SETTINGS, client=client)

    assert client.requests == []


# ---- Retries ----


def test_transient_errors_are_retried(monkeypatch):
    waits = []
    monkeypatch.setattr(gemini, "sleep", waits.append)
    client = FakeClient(StatusError(503), StatusError(429), interaction([]))

    result = extract_menu(png_bytes(), "image/png", settings=SETTINGS, client=client)

    assert result["meta"]["attempts"] == 3
    assert waits == [5, 10]


def test_client_errors_are_not_retried():
    client = FakeClient(StatusError(400), interaction([]))

    with pytest.raises(ModelCallError) as info:
        extract_menu(png_bytes(), "image/png", settings=SETTINGS, client=client)

    assert info.value.attempts == 1


def test_retries_give_up_after_max_attempts():
    client = FakeClient(StatusError(500), StatusError(500), StatusError(500), interaction([]))

    with pytest.raises(ModelCallError, match="after 3 attempts") as info:
        extract_menu(png_bytes(), "image/png", settings=SETTINGS, client=client)

    assert info.value.attempts == 3


def test_hung_call_hits_wall_timeout_and_retries_on_a_new_client(monkeypatch):
    release = threading.Event()
    hung = FakeClient(lambda: release.wait(5))
    fresh = FakeClient(interaction([]))
    monkeypatch.setattr(gemini, "make_client", lambda settings: fresh)
    settings = ExtractionSettings(
        api_key="test-key", model="m", thinking_level="medium", max_attempts=2, wall_timeout_s=0.05
    )

    try:
        result = extract_menu(png_bytes(), "image/png", settings=settings, client=hung)
    finally:
        release.set()

    assert result["meta"]["attempts"] == 2
    assert len(fresh.requests) == 1


# ---- Settings ----

ENV_NAMES = (
    "GEMINI_API_KEY", "EXTRACTION_MODEL", "EXTRACTION_THINKING_LEVEL",
    "EXTRACTION_MAX_ATTEMPTS", "EXTRACTION_REQUEST_TIMEOUT_S", "EXTRACTION_WALL_TIMEOUT_S",
)


@pytest.fixture
def env(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "secret-test-key")
    monkeypatch.setenv("EXTRACTION_MODEL", "gemini-3.5-flash-lite")
    monkeypatch.setenv("EXTRACTION_THINKING_LEVEL", "medium")
    return monkeypatch


def test_settings_defaults_are_p14_values(env):
    settings = load_settings()

    assert (settings.max_attempts, settings.request_timeout_s, settings.wall_timeout_s) == (6, 300, 330)
    assert "secret-test-key" not in repr(settings)


def test_settings_overrides(env):
    env.setenv("EXTRACTION_MAX_ATTEMPTS", "2")
    env.setenv("EXTRACTION_REQUEST_TIMEOUT_S", "60")
    env.setenv("EXTRACTION_WALL_TIMEOUT_S", "90.5")

    settings = load_settings()

    assert (settings.max_attempts, settings.request_timeout_s, settings.wall_timeout_s) == (2, 60, 90.5)


def test_missing_settings_are_named(env):
    env.delenv("GEMINI_API_KEY")
    env.delenv("EXTRACTION_MODEL")

    with pytest.raises(ExtractionConfigError, match="GEMINI_API_KEY, EXTRACTION_MODEL"):
        load_settings()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("EXTRACTION_THINKING_LEVEL", "max"),
        ("EXTRACTION_MAX_ATTEMPTS", "0"),
        ("EXTRACTION_MAX_ATTEMPTS", "2.5"),
        ("EXTRACTION_WALL_TIMEOUT_S", "abc"),
    ],
)
def test_invalid_settings(env, name, value):
    env.setenv(name, value)

    with pytest.raises(ExtractionConfigError, match=name):
        load_settings()


def test_extract_menu_reads_settings_from_env(env):
    client = FakeClient(interaction([]))

    result = extract_menu(png_bytes(), "image/png", client=client)

    assert result["meta"]["model"] == "gemini-3.5-flash-lite"
    assert client.requests[0]["generation_config"] == {"thinking_level": "medium"}
