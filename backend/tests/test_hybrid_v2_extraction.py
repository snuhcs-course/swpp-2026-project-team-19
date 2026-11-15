"""Hybrid extraction with prompt v2 (I4-P12): categories, and non-whisky lines kept out of the
extracted items. CLOVA and Gemini are fakes; no test calls a real API."""

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app import extraction
from app.adapters.extraction import ExtractionError
from app.adapters.hybrid_extraction import HybridMenuExtractor, in_menu_order
from app.extraction import gemini, hybrid, hybrid_v2
from app.models import LineType, MenuItemKind
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
    assert result["itemSources"] == [{"itemOrder": 1, "menuOrder": 1, "nameLines": ["L002"], "priceLines": ["L003"],
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


def test_rows_that_are_neighbours_only_after_filtering_are_not_merged():
    # glass row, a line of another category, bottle row of the same name: two menu lines, not one
    out = convert({"items": [
        item("페른홀로우 12년", "whisky", 15000, "glass", name_lines=["L002"]),
        item("페른홀로우 하이볼", "cocktail", 12000, "glass", name_lines=["L004"]),
        item("페른홀로우 12년", "whisky", 150000, "bottle", name_lines=["L003"]),
        item("하우스 와인", "other", 9000, "glass"),
        item("페른홀로우 하이볼", "cocktail", 90000, "bottle", name_lines=["L005"]),
    ]})
    assert [(i["itemOrder"], i["rawText"], [o["optionLabel"] for o in i["options"]]) for i in out["items"]] == [
        (1, "페른홀로우 12년", ["잔"]), (2, "페른홀로우 12년", ["병"])]
    assert [(s["itemOrder"], s["nameLines"]) for s in out["itemSources"]] == [(1, ["L002"]), (2, ["L003"])]
    assert [(o["itemOrder"], o["rawText"], [x["optionLabel"] for x in o["options"]], o["nameLines"])
            for o in out["otherItems"]] == [
        (1, "페른홀로우 하이볼", ["잔"], ["L004"]), (2, "하우스 와인", ["잔"], []), (3, "페른홀로우 하이볼", ["병"], ["L005"])]


def test_glass_and_bottle_rows_of_one_printed_line_are_joined_when_apart():
    # all glass rows first, then all bottle rows: the rows of one line share their OCR name line
    out = convert({"items": [
        item("페른홀로우 12년", "whisky", 15000, "glass", name_lines=["L002"], price_lines=["L003"]),
        item("페른홀로우 하이볼", "cocktail", 12000, "glass", name_lines=["L004"], price_lines=["L005"]),
        item("하우스 와인", "other", 9000, "glass", name_lines=["L001"]),
        item("페른홀로우 12년", "whisky", 150000, "bottle", name_lines=["L002"], price_lines=["L003"]),
        item("하우스 와인", "other", 45000, "bottle", name_lines=["L001"]),
    ]})
    assert [(i["itemOrder"], i["rawText"], [o["optionLabel"] for o in i["options"]]) for i in out["items"]] == [
        (1, "페른홀로우 12년", ["잔", "병"])]
    assert out["itemSources"] == [{"itemOrder": 1, "menuOrder": 1, "nameLines": ["L002"], "priceLines": ["L003"],
                                   "box": [100, 100, 880, 120]}]
    assert [(o["rawText"], [x["optionLabel"] for x in o["options"]]) for o in out["otherItems"]] == [
        ("페른홀로우 하이볼", ["잔"]), ("하우스 와인", ["잔", "병"])]


def test_rows_apart_stay_apart_without_the_same_name_line():
    # different name lines, no name lines, or another category: two lines of the same name
    for first, second in (
        (item("A", "whisky", 9000, "glass", name_lines=["L002"]), item("A", "whisky", 90000, "bottle", name_lines=["L004"])),
        (item("A", "whisky", 9000, "glass"), item("A", "whisky", 90000, "bottle")),
        (item("A", "whisky", 9000, "glass", name_lines=["L002"]), item("A", "other", 90000, "bottle", name_lines=["L002"])),
        # the same option twice is not one line's two prices
        (item("A", "whisky", 9000, "glass", name_lines=["L002"]), item("A", "whisky", 9500, "glass", name_lines=["L002"])),
    ):
        out = convert({"items": [first, item("B", "food", 5000, None), second]})
        assert len(out["items"]) + len(out["otherItems"]) == 3  # A, B, A: nothing joined


def test_a_line_with_three_prices_is_one_item():
    # "Glass 20ml / 40ml / Bottle": group_items pairs only the 40ml glass with the bottle
    rows = [item("글렌드로낙 12년", "whisky", 12000, "glass", name_lines=["L002"]),
            item("글렌드로낙 12년", "whisky", 22000, "glass", name_lines=["L002"]),
            item("글렌드로낙 12년", "whisky", 180000, "bottle", name_lines=["L002"])]
    rows[0]["pour_ml"], rows[1]["pour_ml"] = 20, 40
    out = convert({"items": rows})
    [only] = out["items"]
    assert [(o["optionLabel"], o["pourMl"], o["priceKrw"]) for o in only["options"]] == [
        ("잔", 20, 12000), ("잔", 40, 22000), ("병", None, 180000)]
    assert out["itemSources"][0]["nameLines"] == ["L002"]


def test_adjacent_glass_and_bottle_rows_are_still_one_line():
    out = convert(V2_OUTPUT)
    assert [[o["optionLabel"] for o in i["options"]] for i in out["items"]] == [["잔", "병"]]
    wine = next(o for o in out["otherItems"] if o["rawText"] == "하우스 와인")
    assert [o["optionLabel"] for o in wine["options"]] == ["잔", "병"]
    # a whisky row and a non-whisky row of the same name are never one line
    out = convert({"items": [item("A", "whisky", 9000, "glass"), item("A", "other", 90000, "bottle")]})
    assert len(out["items"]) == 1 and len(out["otherItems"]) == 1


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


def test_every_line_has_its_place_in_the_menu():
    out = convert({"items": [
        item("치즈 플래터", "food", 25000, None),
        item("페른홀로우 12년", "whisky", 15000, "glass", name_lines=["L002"], price_lines=["L003"]),
        item("x" * 201, "cocktail", 9000, "glass"),                      # dropped: leaves a gap
        item("페른홀로우 하이볼", "cocktail", 12000, "glass", name_lines=["L004"], price_lines=["L005"]),
        item("스톤브리지 10년", "whisky", 16000, "glass"),
    ]})

    assert [(s["itemOrder"], s["menuOrder"]) for s in out["itemSources"]] == [(1, 2), (2, 5)]
    assert [(o["itemOrder"], o["menuOrder"], o["rawText"]) for o in out["otherItems"]] == [
        (1, 1, "치즈 플래터"), (2, 4, "페른홀로우 하이볼")]
    assert out["otherItemsDropped"] == 1


def test_adapter_with_prompt_v2_gives_every_line_in_menu_order(monkeypatch, fake_ocr, fake_gemini):
    monkeypatch.setenv("EXTRACTION_HYBRID_PROMPT", "v2")
    extractor = HybridMenuExtractor(SETTINGS, CLOVA)
    assert extractor.pipeline_version == "bottlemap-menu-hybrid-prompthybrid-v2-thinking-medium"

    result = extractor.extract(jpeg(), "image/jpeg", "menu.jpg")

    # result.items is what the import stores as extracted_items; only kind whisky is matched
    assert [(i.item_order, i.raw_text, i.kind, i.line_type) for i in result.items] == [
        (1, "페른홀로우 12년", MenuItemKind.WHISKY, LineType.PRODUCT),
        (2, "페른홀로우 하이볼", MenuItemKind.OTHER, LineType.PRODUCT),
        (3, "치즈 플래터", MenuItemKind.OTHER, LineType.PRODUCT),
        (4, "하우스 와인", MenuItemKind.OTHER, LineType.PRODUCT),
    ]
    highball, cheese, wine = result.items[1:]
    assert highball.product_name == "페른홀로우 하이볼" and (highball.brand_text, highball.age_years) == (None, None)
    assert [(o.option_label, o.pour_ml, o.price_krw) for o in highball.options] == [("잔", None, 12000)]
    assert cheese.options[0].price_krw == 25000
    assert [(o.option_label, o.pour_ml, o.price_krw) for o in wine.options] == [("잔", 120, 9000), ("병", None, 45000)]
    # every line has its source under its new number, for the review screen (this OCR response
    # has the whisky line only, so the other lines have no box)
    sources = result.raw_output["itemSources"]
    assert [(s["itemOrder"], s["menuOrder"], s["nameLines"], s["box"]) for s in sources] == [
        (1, 1, ["L002"], [100, 100, 880, 120]), (2, 2, [], None), (3, 3, [], None), (4, 4, [], None)]
    # the lines as the extraction gave them, with their categories, stay in raw_output
    assert [(o["rawText"], o["category"]) for o in result.raw_output["otherItems"]] == [
        ("페른홀로우 하이볼", "cocktail"), ("치즈 플래터", "food"), ("하우스 와인", "other")]


def test_whisky_lines_between_other_lines_keep_their_place_and_their_boxes(monkeypatch, fake_ocr):
    output = {"items": [
        item("치즈 플래터", "food", 25000, None),
        item("페른홀로우 12년", "whisky", 15000, "glass", name_lines=["L002"], price_lines=["L003"]),
        item("페른홀로우 하이볼", "cocktail", 12000, "glass", name_lines=["L001"]),
        item("스톤브리지 10년", "whisky", 16000, "glass"),
    ]}
    fake = SimpleNamespace(interactions=FakeInteractions(json.dumps(output)))
    monkeypatch.setattr(gemini, "make_client", lambda settings: fake)

    result = HybridMenuExtractor(SETTINGS, CLOVA, prompt="v2").extract(jpeg(), "image/jpeg", None)

    assert [(i.item_order, i.raw_text, i.kind.value) for i in result.items] == [
        (1, "치즈 플래터", "other"), (2, "페른홀로우 12년", "whisky"), (3, "페른홀로우 하이볼", "other"),
        (4, "스톤브리지 10년", "whisky")]
    assert [(s["itemOrder"], s["box"]) for s in result.raw_output["itemSources"]] == [
        (1, None), (2, [100, 100, 880, 120]), (3, [100, 10, 260, 30]), (4, None)]


def test_in_menu_order_leaves_a_result_without_other_lines_as_it_is():
    items, meta = [{"itemOrder": 1, "rawText": "a"}], {"itemSources": [{"itemOrder": 1, "box": None}]}
    assert in_menu_order(items, meta) == (items, meta)                                   # prompt v1
    assert in_menu_order(items, {**meta, "otherItems": []})[0] is items                  # v2, whisky only
    assert in_menu_order(items, {**meta, "otherItems": None})[1]["itemSources"] is meta["itemSources"]


def test_in_menu_order_puts_lines_without_a_place_after_the_others():
    """A result recorded before menuOrder existed: whisky first, then the other lines, as given."""
    items = [{"itemOrder": 1, "rawText": "위스키 A"}, {"itemOrder": 2, "rawText": "위스키 B"}]
    meta = {"itemSources": [{"itemOrder": 2, "nameLines": ["L9"], "priceLines": [], "box": [1, 2, 3, 4]}],
            "otherItems": [{"itemOrder": 1, "rawText": "안주", "options": [], "nameLines": [], "priceLines": [],
                            "box": None}]}

    payload, merged = in_menu_order(items, meta)

    assert [(i["itemOrder"], i["rawText"], i.get("kind")) for i in payload] == [
        (1, "위스키 A", None), (2, "위스키 B", None), (3, "안주", "other")]
    # 위스키 A had no source and gets none; the others keep theirs under the new numbers
    assert merged["itemSources"] == [
        {"itemOrder": 2, "nameLines": ["L9"], "priceLines": [], "box": [1, 2, 3, 4], "menuOrder": None},
        {"itemOrder": 3, "nameLines": [], "priceLines": [], "box": None, "menuOrder": None}]
    assert meta["itemSources"][0]["itemOrder"] == 2 and "menuOrder" not in meta["itemSources"][0]  # not changed in place


def test_adapter_with_prompt_v1_gives_whisky_items_only(monkeypatch, fake_ocr):
    v1 = {"items": [{k: v for k, v in row.items() if k != "category"} for row in V2_OUTPUT["items"][:2]]}
    fake = SimpleNamespace(interactions=FakeInteractions(json.dumps(v1)))
    monkeypatch.setattr(gemini, "make_client", lambda settings: fake)

    result = HybridMenuExtractor(SETTINGS, CLOVA, prompt="v1").extract(jpeg(), "image/jpeg", None)

    assert [(i.raw_text, i.kind) for i in result.items] == [("페른홀로우 12년", MenuItemKind.WHISKY)]
    assert "otherItems" not in result.raw_output and "menuOrder" not in result.raw_output["itemSources"][0]


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
