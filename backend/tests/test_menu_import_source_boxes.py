"""source_boxes(): the review screen's line boxes read from an extraction run's raw_output."""

import pytest

from app.services.menu_import_review import source_boxes


def test_hybrid_item_sources_give_a_box_per_item_order():
    raw_output = {
        "mode": "hybrid",
        "itemSources": [
            {"itemOrder": 1, "nameLines": ["L001"], "priceLines": ["L002"], "box": [100, 100, 880, 120]},
            {"itemOrder": 2, "nameLines": [], "priceLines": [], "box": None},
            {"itemOrder": 3, "nameLines": ["L004"], "priceLines": [], "box": [0, 990, 1000, 1000]},
        ],
    }

    assert source_boxes(raw_output) == {1: [100, 100, 880, 120], 3: [0, 990, 1000, 1000]}


@pytest.mark.parametrize(
    "raw_output",
    [
        None,
        [],
        {},
        {"itemSources": None},
        {"itemSources": "L001"},
        {"hybridFallback": {"reason": "CLOVA down"}, "items": []},
    ],
)
def test_runs_without_item_sources_have_no_boxes(raw_output):
    assert source_boxes(raw_output) == {}


@pytest.mark.parametrize(
    "source",
    [
        "L001",
        {"box": [1, 2, 3, 4]},
        {"itemOrder": "1", "box": [1, 2, 3, 4]},
        {"itemOrder": True, "box": [1, 2, 3, 4]},
        {"itemOrder": 1, "box": [1, 2, 3]},
        {"itemOrder": 1, "box": [1, 2, 3, 4, 5]},
        {"itemOrder": 1, "box": [1.5, 2, 3, 4]},
        {"itemOrder": 1, "box": [False, 2, 3, 4]},
        {"itemOrder": 1, "box": [-1, 2, 3, 4]},
        {"itemOrder": 1, "box": [1, 2, 3, 1001]},
        {"itemOrder": 1, "box": [5, 2, 5, 4]},
        {"itemOrder": 1, "box": [1, 4, 3, 4]},
        {"itemOrder": 1, "box": [3, 2, 1, 4]},
        {"itemOrder": 1, "box": "1,2,3,4"},
    ],
)
def test_entries_of_another_shape_are_skipped(source):
    assert source_boxes({"itemSources": [source, {"itemOrder": 2, "box": [1, 2, 3, 4]}]}) == {2: [1, 2, 3, 4]}
