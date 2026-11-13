"""Hybrid extraction with prompt v2 (I4-P12): categories, and non-whisky lines kept out of the
extracted items. CLOVA and Gemini are fakes; no test calls a real API."""

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app import extraction
from app.adapters.extraction import ExtractionError
from app.adapters.hybrid_extraction import HybridMenuExtractor
from app.extraction import gemini, hybrid, hybrid_v2
from tests.test_hybrid_extraction_adapter import CLOVA, OCR_RESPONSE, SETTINGS, FakeInteractions, jpeg

TABLE = [{"id": "L001", "box": [100, 10, 260, 30], "text": "WHISKY"},
         {"id": "L002", "box": [100, 100, 380, 120], "text": "페른홀로우 12년"},
         {"id": "L003", "box": [600, 100, 880, 120], "text": "15,000 150,000"},
         {"id": "L004", "box": [100, 200, 380, 220], "text": "페른홀로우 하이볼"},
         {"id": "L005", "box": [600, 200, 700, 220], "text": "12,000"}]


def item(name, category, price=15000, unit="glass", pour=None, name_lines=(), price_lines=()):
    return {"raw_name": name, "price_krw": price, "pour_ml": pour, "unit": unit,
            "source_lines": {"name": list(name_lines), "price": list(price_lines)}, "category": category}


V2_OUTPUT = {"items": [
    item("페른홀로우 12년", "whisky", 15000, "glass", name_lines=["L002"], price_lines=["L003"]),
    item("페른홀로우 12년", "whisky", 150000, "bottle", name_lines=["L002"], price_lines=["L003"]),
    item("페른홀로우 하이볼", "cocktail", 12000, "glass", name_lines=["L004"], price_lines=["L005"]),
    item("치즈 플래터", "food", 25000, None),
    item("하우스 와인", "other", 9000, "glass", pour=120),
    item("하우스 와인", "other", 45000, "bottle"),
]}


@pytest.fixture
def fake_gemini(monkeypatch):
    fake = SimpleNamespace(interactions=FakeInteractions(json.dumps(V2_OUTPUT)))
    monkeypatch.setattr(gemini, "make_client", lambda settings: fake)
    return fake.interactions


@pytest.fixture
def fake_ocr(monkeypatch):
    calls = []

    def fake(settings, image, mime_type, client=None):
        calls.append(mime_type)
        return {"response": OCR_RESPONSE, "sentSize": [1000, 2000], "latencyMs": 900, "attempts": 1}

    monkeypatch.setattr(hybrid, "call_ocr", fake)
    return calls


def convert(output, table=TABLE):
    return hybrid_v2.convert_output(json.dumps(output), table)


# ---- convert_output ----


def test_only_whisky_lines_become_items():
    result = convert(V2_OUTPUT)
    assert [(i["rawText"], i["lineType"], len(i["options"])) for i in result["items"]] == [("페른홀로우 12년", "product", 2)]
    assert result["itemSources"] == [{"itemOrder": 1, "nameLines": ["L002"], "priceLines": ["L003"],
                                      "box": [100, 100, 880, 120]}]
    assert result["rawOutput"] == V2_OUTPUT and result["otherItemsDropped"] == 0


def test_other_lines_keep_name_category_options_and_box_in_output_order():
    others = convert(V2_OUTPUT)["otherItems"]
    assert [(o["itemOrder"], o["rawText"], o["category"]) for o in others] == [
        (1, "페른홀로우 하이볼", "cocktail"), (2, "치즈 플래터", "food"), (3, "하우스 와인", "other")]
    assert others[0]["options"] == [{"optionLabel": "잔", "pourMl": None, "priceKrw": 12000}]
    assert others[0]["nameLines"] == ["L004"] and others[0]["box"] == [100, 200, 700, 220]
    assert others[1]["options"] == [{"optionLabel": None, "pourMl": None, "priceKrw": 25000}] and others[1]["box"] is None
    # glass and bottle rows of one line are one item, as for whisky
    assert others[2]["options"] == [{"optionLabel": "잔", "pourMl": 120, "priceKrw": 9000},
                                    {"optionLabel": "병", "pourMl": None, "priceKrw": 45000}]


def test_a_cocktail_named_like_a_whisky_is_not_an_item():
    result = convert({"items": [item("페른홀로우 12년", "cocktail")]})
    assert result["items"] == [] and [o["rawText"] for o in result["otherItems"]] == ["페른홀로우 12년"]


def test_a_menu_without_whisky_gives_no_items():
    result = convert({"items": [item("모히토", "cocktail"), item("감자튀김", "food", unit=None)]})
    assert result["items"] == [] and len(result["otherItems"]) == 2


def test_an_unusable_other_line_is_dropped_and_the_whisky_lines_stay():
    bad = [item("값이 0인 칵테일", "cocktail", price=0), item("긴" * 201, "food", unit=None), item("  ", "other")]
    result = convert({"items": [V2_OUTPUT["items"][0], *bad, item("모히토", "cocktail")]})
    assert len(result["items"]) == 1
    assert [o["rawText"] for o in result["otherItems"]] == ["모히토"] and result["otherItemsDropped"] == 3
    assert result["otherItems"][0]["itemOrder"] == 1


def test_an_other_line_without_price_or_unit_has_no_options():
    result = convert({"items": [item("시가 메뉴", "food", price=None, unit=None)]})
    assert result["otherItems"][0]["options"] == []


@pytest.mark.parametrize("output", [
    {"items": [item("이름", "beer")]},                         # not a category
    {"items": [{k: v for k, v in item("이름", "whisky").items() if k != "category"}]},  # v1 output
    {"items": [item("값이 0인 위스키", "whisky", price=0)]},     # a whisky line still fails the photo
])
def test_invalid_answers_are_rejected(output):
    with pytest.raises(ValidationError):
        convert(output)


def test_prompt_v2_is_v1_with_categories_instead_of_the_exclusion():
    v1, v2 = hybrid.load_prompt(), hybrid_v2.load_prompt()
    assert "하위 항목은 제외한다" in v1 and "하위 항목은 제외한다" not in v2
    assert all(c in v2 for c in ('"whisky"', '"cocktail"', '"food"', '"other"'))
    # the rules for names, prices, units and source lines are the v1 text
    for line in ("**글자 철자와 가격 숫자는 OCR 줄을 근거로 한다.**", "| 열 제목 없는 가격 두 개 |", "- 세트·테이스팅 플라이트"):
        assert line in v1 and line in v2
    assert "\r" not in v2


# ---- extract_menu_hybrid_v2 ----


def test_request_uses_prompt_v2_and_its_schema(fake_ocr, fake_gemini):
    result = hybrid_v2.extract_menu_hybrid_v2(jpeg(), "image/jpeg", CLOVA, settings=SETTINGS)
    request = fake_gemini.requests[0]
    assert request["system_instruction"] == hybrid_v2.load_prompt()
    assert request["input"][0]["text"].startswith(hybrid.USER_HEADER)
    assert "category" in json.dumps(request)
    meta = result["meta"]
    assert meta["promptVersion"] == "hybrid-v2" and meta["mode"] == "hybrid"
    assert [i["rawText"] for i in result["items"]] == ["페른홀로우 12년"]
    assert [o["category"] for o in meta["otherItems"]] == ["cocktail", "food", "other"]
    assert meta["otherItemsDropped"] == 0 and meta["outputTokens"] == 300


@pytest.mark.parametrize("text, status, message", [
    ("{oops", "completed", "not valid hybrid v2 output"),
    (json.dumps(V2_OUTPUT), "failed", "interaction status is 'failed'"),
])
def test_invalid_output(fake_ocr, monkeypatch, text, status, message):
    fake = SimpleNamespace(interactions=FakeInteractions(text, status))
    monkeypatch.setattr(gemini, "make_client", lambda settings: fake)
    with pytest.raises(extraction.InvalidModelOutputError, match=message) as error:
        hybrid_v2.extract_menu_hybrid_v2(jpeg(), "image/jpeg", CLOVA, settings=SETTINGS)
    assert error.value.raw_text == text and error.value.meta["promptVersion"] == "hybrid-v2"


# ---- adapter ----


def test_adapter_defaults_to_prompt_v1(monkeypatch):
    monkeypatch.delenv("EXTRACTION_HYBRID_PROMPT", raising=False)
    extractor = HybridMenuExtractor(SETTINGS, CLOVA)
    assert extractor.prompt == "v1" and "prompthybrid-v1-" in extractor.pipeline_version


def test_adapter_with_prompt_v2_stores_only_whisky_items(monkeypatch, fake_ocr, fake_gemini):
    monkeypatch.setenv("EXTRACTION_HYBRID_PROMPT", "v2")
    extractor = HybridMenuExtractor(SETTINGS, CLOVA)
    assert extractor.pipeline_version == "bottlemap-menu-hybrid-prompthybrid-v2-thinking-medium"
    result = extractor.extract(jpeg(), "image/jpeg", "menu.jpg")
    # result.items is what the import stores as extracted_items and sends to matching
    assert [i.raw_text for i in result.items] == ["페른홀로우 12년"]
    assert [o["rawText"] for o in result.raw_output["otherItems"]] == ["페른홀로우 하이볼", "치즈 플래터", "하우스 와인"]


def test_adapter_rejects_an_unknown_prompt(monkeypatch):
    monkeypatch.setenv("EXTRACTION_HYBRID_PROMPT", "v9")
    with pytest.raises(extraction.ExtractionConfigError, match="EXTRACTION_HYBRID_PROMPT"):
        HybridMenuExtractor(SETTINGS, CLOVA)


def test_adapter_v2_errors_fail_the_run_like_v1(monkeypatch, fake_ocr):
    fake = SimpleNamespace(interactions=FakeInteractions("{oops"))
    monkeypatch.setattr(gemini, "make_client", lambda settings: fake)
    with pytest.raises(ExtractionError, match="hybrid v2") as error:
        HybridMenuExtractor(SETTINGS, CLOVA, prompt="v2").extract(jpeg(), "image/jpeg", "menu.jpg")
    assert error.value.raw_output["rawText"] == "{oops"
