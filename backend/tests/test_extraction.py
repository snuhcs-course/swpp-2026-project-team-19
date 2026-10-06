import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.adapters.extraction import (
    ExtractionError,
    MockMenuExtractor,
    load_fixture,
    parse_extraction_response,
)
from app.models import LineType

LABELS_PATH = Path(__file__).resolve().parents[2] / "eval" / "labels_v1.json"

VALID_ITEM = {
    "itemOrder": 1,
    "rawText": "딘스톤 12년 15ml 8.0 / 30ml 15.0",
    "lineType": "product",
    "productName": "딘스톤 12년",
    "brandText": "딘스톤",
    "ageYears": 12,
    "editionName": None,
    "abv": 46.3,
    "options": [{"optionLabel": None, "pourMl": 15, "priceKrw": 8000}],
    "confidence": 0.92,
}


def test_parses_the_spec_format():
    [item] = parse_extraction_response({"items": [VALID_ITEM]})

    assert (item.item_order, item.line_type, item.product_name, item.age_years) == (1, LineType.PRODUCT, "딘스톤 12년", 12)
    assert (item.abv, item.confidence) == (Decimal("46.30"), Decimal("0.9200"))
    assert [(o.option_label, o.pour_ml, o.price_krw) for o in item.options] == [(None, 15, 8000)]


def test_optional_fields_may_be_missing():
    [item] = parse_extraction_response({"items": [{"itemOrder": 3, "rawText": "SINGLE MALT", "lineType": "section_header"}]})

    assert (item.product_name, item.options, item.confidence) == (None, (), None)


@pytest.mark.parametrize(
    "change",
    [
        {"lineType": "drink"},
        {"lineType": None},
        {"itemOrder": 0},
        {"itemOrder": True},
        {"rawText": "  "},
        {"rawText": None},
        {"productName": "x" * 201},
        {"ageYears": -1},
        {"abv": 120},
        {"confidence": 1.5},
        {"options": [{"priceKrw": -1000}]},
        {"options": [{"priceKrw": 9.5}]},
        {"options": [{"pourMl": 0}]},
        {"options": "15ml"},
    ],
)
def test_invalid_items_are_rejected(change):
    with pytest.raises(ExtractionError):
        parse_extraction_response({"items": [{**VALID_ITEM, **change}]})


@pytest.mark.parametrize("payload", [None, [], {"items": None}, {"items": ["x"]}])
def test_invalid_payload_shapes_are_rejected(payload):
    with pytest.raises(ExtractionError):
        parse_extraction_response(payload)


def test_repeated_item_order_is_rejected():
    with pytest.raises(ExtractionError):
        parse_extraction_response({"items": [VALID_ITEM, copy.deepcopy(VALID_ITEM)]})


@pytest.mark.parametrize(
    ("filename", "fixture"),
    [("menu.jpg", "label"), (None, "label"), ("SAMPLE-1.png", "sample"), ("my_sample.heic", "sample")],
)
def test_mock_chooses_the_fixture_by_file_name(filename, fixture):
    result = MockMenuExtractor().extract(b"image", "image/jpeg", filename)

    assert result.raw_output == load_fixture(fixture)
    assert len(result.items) == len(load_fixture(fixture)["items"])


@pytest.mark.parametrize("filename", ["fail.jpg", "sample_FAIL.png"])
def test_mock_fails_when_the_file_name_asks_for_it(filename):
    with pytest.raises(ExtractionError):
        MockMenuExtractor().extract(b"image", "image/jpeg", filename)


def test_sample_fixture_covers_each_review_case():
    items = MockMenuExtractor().extract(b"", "image/png", "sample.png").items

    assert [i.line_type for i in items] == [
        LineType.SECTION_HEADER,
        LineType.PRODUCT,
        LineType.PRODUCT,
        LineType.PRODUCT,
        LineType.DESCRIPTION,
    ]
    # Same alias as item 2 but a conflicting age, so matching must not auto-confirm it.
    assert (items[2].product_name, items[2].age_years) == ("Glenfiddich 12", 15)


@pytest.mark.skipif(not LABELS_PATH.exists(), reason="eval labels are not checked out")
def test_label_fixture_matches_the_labeled_photo():
    labels = json.loads(LABELS_PATH.read_text(encoding="utf-8"))
    photo = next(p for p in labels["photos"] if p["photo_id"] == "008_서로상_01")
    unit_label = {"glass": "잔", "bottle": "병"}
    expected = [(row["raw_name"], unit_label[row["unit"]], row["price_krw"]) for row in photo["items"]]

    products = [i for i in MockMenuExtractor().extract(b"", "image/jpeg", "menu.jpg").items if i.line_type == LineType.PRODUCT]

    assert [(i.product_name, o.option_label, o.price_krw) for i in products for o in i.options] == expected
