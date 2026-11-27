"""The facing-page guard (I5-P19, app.extraction.edge_guard): whisky lines without a price whose OCR
name lines lie wholly in the left or right 10% strip of the photo are dropped and recorded. No test
calls a real API: the route ladder is replaced by a fixed result, and the PDFs are those of
test_pdf_extraction."""

import json
import logging
from dataclasses import replace
from pathlib import Path

import pytest

from app.adapters import openrouter_extraction
from app.adapters.openrouter_extraction import OpenRouterMenuExtractor
from app.adapters.pdf_routed_extraction import RoutedPdfMenuExtractor
from app.api import deps
from app.extraction import edge_guard, pdf, routed
from app.extraction.edge_guard import drop_edge_rows, has_price, in_edge_strip, load_strip_permille, name_box
from app.extraction.errors import ExtractionConfigError
from tests.test_hybrid_extraction_adapter import CLOVA, jpeg
from tests.test_openrouter_extraction import ENV, ROUTE, set_openrouter_env

FIXTURES = Path(__file__).resolve().parent / "fixtures"
# 67 whisky lines without a price from the recorded answers: 60 of the page next to
# 011_mirabeau_03 and 7 of the photos' own menus (ai/runs/2026-11-27_i5_pr_prep/report.md, B)
RECORDED = json.loads((FIXTURES / "edge_guard_rows.json").read_text(encoding="utf-8"))["rows"]


def option(price=None, label=None, pour=None):
    return {"optionLabel": label, "pourMl": pour, "priceKrw": price}


def line(name, box, *options, price_box=None):
    """One whisky line: (item, its OCR name line, its OCR price line or None)."""
    return name, box, list(options), price_box


def answer(*lines, other_items=None):
    """items and meta as hybrid_v2.convert_output and routed.extract_menu_routed give them."""
    items, sources, table = [], [], []
    for order, (name, box, options, price_box) in enumerate(lines, start=1):
        name_lines = [] if box is None else [f"N{order:03d}"]
        price_lines = [] if price_box is None else [f"P{order:03d}"]
        if box is not None:
            table.append({"id": f"N{order:03d}", "box": box, "text": name})
        if price_box is not None:
            table.append({"id": f"P{order:03d}", "box": price_box, "text": "15,000"})
        items.append({"itemOrder": order, "rawText": name, "lineType": "product", "productName": name,
                      "brandText": None, "ageYears": None, "editionName": None, "abv": None,
                      "options": options, "confidence": None})
        sources.append({"itemOrder": order, "nameLines": name_lines, "priceLines": price_lines,
                        "box": box, "menuOrder": order})
    meta = {"mode": "hybrid", "ocr": {"lines": table}, "itemSources": sources,
            "otherItems": other_items or [], "otherItemsDropped": 0, "route": {"stage": 0}}
    return items, meta


# ---- the rule on the recorded lines ----


def test_the_recorded_lines_the_60_of_the_next_page_are_dropped_and_the_7_of_the_menu_kept():
    items, meta = answer(*(line(row["name"], row["box"]) for row in RECORDED))

    kept, out = drop_edge_rows(items, meta, 100)

    kinds = [row["kind"] for row in RECORDED]
    dropped = [kinds[row["itemOrder"] - 1] for row in out["droppedEdgeRows"]]
    assert dropped == ["neighbour"] * 60
    assert [item["rawText"] for item in kept] == [row["name"] for row in RECORDED if row["kind"] == "label"]


def test_the_recorded_lines_with_a_glass_mark_are_dropped_the_same_way():
    # 24 of the 60 lines came with unit glass and no price: an option without a price is no price
    items, meta = answer(*(line(row["name"], row["box"], option(label="잔")) for row in RECORDED))

    kept, out = drop_edge_rows(items, meta, 100)

    assert len(out["droppedEdgeRows"]) == 60 and len(kept) == 7


def test_a_wider_strip_starts_to_drop_lines_of_the_menu():
    # the margin is not wide: at 150 the three Ardbeg Anthology lines of 014_tale_07 go too
    items, meta = answer(*(line(row["name"], row["box"]) for row in RECORDED))

    kept, out = drop_edge_rows(items, meta, 150)

    assert {row["rawText"] for row in out["droppedEdgeRows"]} - {r["name"] for r in RECORDED if r["kind"] == "neighbour"} == {
        "Ardbeg Anthology"}
    assert len(kept) == 4


# ---- what is kept ----


@pytest.mark.parametrize("options", [
    [option(price=15000)],
    [option(price=15000, label="잔"), option(label="병")],  # one priced option is enough
    [option(price=0)],
])
def test_a_line_with_a_price_in_the_strip_is_kept(options):
    items, meta = answer(line("발베니 12년", [920, 100, 1000, 130], *options))

    kept, out = drop_edge_rows(items, meta, 100)

    assert kept == items and out["droppedEdgeRows"] == []


@pytest.mark.parametrize("options", [[], [option(label="잔")], [option(pour=30)], [option(label="잔"), option(label="병")]])
def test_a_line_without_a_price_in_the_strip_is_dropped_whatever_else_it_has(options):
    items, meta = answer(line("하이랜드 파크 12년", [905, 73, 1000, 109], *options))

    kept, out = drop_edge_rows(items, meta, 100)

    assert kept == [] and [row["rawText"] for row in out["droppedEdgeRows"]] == ["하이랜드 파크 12년"]


def test_a_line_without_ocr_name_lines_is_kept():
    items, meta = answer(line("사진에서만 읽은 줄", None))

    kept, out = drop_edge_rows(items, meta, 100)

    assert kept == items and out["droppedEdgeRows"] == []


def test_a_line_without_a_source_entry_is_kept():
    items, meta = answer(line("하이랜드 파크 12년", [905, 73, 1000, 109]))
    meta = {**meta, "itemSources": []}

    kept, out = drop_edge_rows(items, meta, 100)

    assert kept == items and out["droppedEdgeRows"] == [] and out["itemSources"] == []


def test_a_meta_without_ocr_lines_keeps_every_line():
    items, meta = answer(line("하이랜드 파크 12년", [905, 73, 1000, 109]))
    del meta["ocr"]

    kept, out = drop_edge_rows(items, meta, 100)

    assert kept == items and out["droppedEdgeRows"] == []


@pytest.mark.parametrize("box, inside", [
    ([900, 0, 1000, 50], True),     # the right strip starts at 900
    ([899, 0, 1000, 50], False),    # reaches out of it
    ([0, 0, 100, 50], True),        # the left strip ends at 100
    ([0, 0, 101, 50], False),
    ([450, 0, 550, 50], False),     # the middle
    ([0, 0, 1000, 50], False),      # touches both edges but lies in neither strip
])
def test_the_whole_name_box_must_lie_in_one_strip(box, inside):
    assert in_edge_strip(box, 100) is inside


def test_a_strip_of_0_drops_nothing():
    items, meta = answer(*(line(row["name"], row["box"]) for row in RECORDED), line("가장자리", [1000, 0, 1000, 10]))

    kept, out = drop_edge_rows(items, meta, 0)

    assert kept == items and out["droppedEdgeRows"] == [] and out["edgeStripPermille"] == 0
    assert not in_edge_strip([0, 0, 0, 10], 0)


def test_the_box_is_that_of_the_name_lines_only():
    # a price line in the middle of the photo does not pull the name out of the strip
    items, meta = answer(line("하이랜드 파크 12년", [905, 73, 1000, 109], option(label="잔"), price_box=[500, 73, 560, 109]))
    meta["itemSources"][0]["nameLines"].append("N999")  # an id the OCR table does not have is left out

    assert name_box(meta["itemSources"][0], {row["id"]: row["box"] for row in meta["ocr"]["lines"]}) == [905, 73, 1000, 109]
    assert name_box(None, {}) is None
    assert drop_edge_rows(items, meta, 100)[1]["droppedEdgeRows"][0]["box"] == [905, 73, 1000, 109]


def test_has_price():
    assert not has_price({"options": []}) and not has_price({"options": [option(label="병", pour=700)]})
    assert has_price({"options": [option(), option(price=90000)]})


# ---- the record ----


def test_a_dropped_line_is_recorded_and_the_kept_lines_are_numbered_again():
    other = [{"itemOrder": 1, "menuOrder": 2, "rawText": "하이볼", "category": "cocktail", "options": [],
              "nameLines": [], "priceLines": [], "box": None}]
    items, meta = answer(line("발베니 12년", [300, 50, 500, 80], option(price=15000)),
                         line("하이랜드 파크 12년", [905, 73, 1000, 109], option(label="잔")),
                         line("맥캘란 12년", [300, 120, 500, 150], option(price=18000)),
                         other_items=other)

    kept, out = drop_edge_rows(items, meta, 100)

    assert [(item["itemOrder"], item["rawText"]) for item in kept] == [(1, "발베니 12년"), (2, "맥캘란 12년")]
    assert [(s["itemOrder"], s["nameLines"], s["menuOrder"]) for s in out["itemSources"]] == [
        (1, ["N001"], 1), (2, ["N003"], 3)]
    assert out["droppedEdgeRows"] == [{"itemOrder": 2, "menuOrder": 2, "rawText": "하이랜드 파크 12년",
                                       "nameLines": ["N002"], "box": [905, 73, 1000, 109]}]
    assert out["edgeStripPermille"] == 100
    assert out["otherItems"] == other and out["route"] == {"stage": 0}  # the rest of the meta is kept
    assert meta["itemSources"][2]["itemOrder"] == 3  # the input is not changed


def test_one_log_line_per_photo_with_the_count(caplog):
    with caplog.at_level(logging.INFO, logger="app.extraction.edge_guard"):
        drop_edge_rows(*answer(line("하이랜드 파크 12년", [905, 73, 1000, 109])), 100)
        drop_edge_rows(*answer(line("발베니 12년", [300, 50, 500, 80])), 100)

    assert [(r.levelno, r.getMessage()) for r in caplog.records] == [
        (logging.WARNING, "extraction edge guard dropped=1 strip_permille=100"),
        (logging.INFO, "extraction edge guard dropped=0 strip_permille=100"),
    ]


# ---- the setting ----


@pytest.fixture
def env(monkeypatch):
    for name in (*ENV, edge_guard.STRIP_SETTING):
        monkeypatch.delenv(name, raising=False)
    deps.get_menu_extractor.cache_clear()
    yield monkeypatch
    deps.get_menu_extractor.cache_clear()


@pytest.mark.parametrize("value, expected", [(None, 100), ("", 100), ("0", 0), ("150", 150), ("499", 499)])
def test_the_strip_setting(env, value, expected):
    if value is not None:
        env.setenv(edge_guard.STRIP_SETTING, value)

    assert load_strip_permille() == expected


@pytest.mark.parametrize("value", ["-1", "500", "1000", "10%", "0.1"])
def test_an_invalid_strip_is_refused(env, value):
    env.setenv(edge_guard.STRIP_SETTING, value)

    with pytest.raises(ExtractionConfigError, match="EXTRACTION_EDGE_STRIP_PERMILLE must be an integer from 0"):
        load_strip_permille()


def test_the_server_reads_the_strip_and_stops_at_start_up_on_an_invalid_one(env):
    set_openrouter_env(env)
    assert deps.get_menu_extractor().route.edge_strip_permille == 100

    deps.get_menu_extractor.cache_clear()
    env.setenv(edge_guard.STRIP_SETTING, "0")
    assert routed.load_route_settings().edge_strip_permille == 0

    env.setenv(edge_guard.STRIP_SETTING, "wide")
    with pytest.raises(RuntimeError, match="MENU_EXTRACTOR=openrouter is not configured: .*EXTRACTION_EDGE_STRIP_PERMILLE"):
        deps.get_menu_extractor()


# ---- where it runs ----

NEXT_PAGE = line("하이랜드 파크 12년", [905, 73, 1000, 109], option(label="잔"))
OWN_LINE = line("발베니 12년", [300, 50, 500, 80], option(price=15000))


@pytest.fixture
def routes(monkeypatch):
    """extract_menu_routed answers every photo with one line of the menu and one of the next page."""
    calls = []

    def fixed(image, mime_type, clova, route, breaker, *, budget=None, ocr_client=None, **kwargs):
        calls.append(ocr_client)
        items, meta = answer(OWN_LINE, NEXT_PAGE)
        return {"items": items, "meta": meta}

    monkeypatch.setattr(openrouter_extraction, "extract_menu_routed", fixed)
    return calls


@pytest.mark.parametrize("stage", [0, 1, 2, 3])
def test_every_route_of_a_photo_goes_through_the_guard_before_the_lines_are_stored(monkeypatch, stage):
    def at_stage(*args, **kwargs):
        items, meta = answer(OWN_LINE, NEXT_PAGE)
        return {"items": items, "meta": {**meta, "route": {"stage": stage}}}

    monkeypatch.setattr(openrouter_extraction, "extract_menu_routed", at_stage)

    result = OpenRouterMenuExtractor(ROUTE, CLOVA).extract(jpeg(), "image/jpeg", "menu.jpg")

    assert [item.raw_text for item in result.items] == ["발베니 12년"]
    assert [row["rawText"] for row in result.raw_output["droppedEdgeRows"]] == ["하이랜드 파크 12년"]
    assert result.raw_output["route"]["stage"] == stage and result.raw_output["edgeStripPermille"] == 100


def test_the_strip_comes_from_the_route_settings(routes):
    result = OpenRouterMenuExtractor(replace(ROUTE, edge_strip_permille=0), CLOVA).extract(jpeg(), "image/jpeg", None)

    assert [item.raw_text for item in result.items] == ["발베니 12년", "하이랜드 파크 12년"]
    assert result.raw_output["droppedEdgeRows"] == [] and result.raw_output["edgeStripPermille"] == 0


def test_extract_with_can_turn_the_guard_off(routes):
    result = OpenRouterMenuExtractor(ROUTE, CLOVA).extract_with(jpeg(), "image/jpeg", CLOVA, None, edge_guard=False)

    assert len(result.items) == 2 and "droppedEdgeRows" not in result.raw_output


def test_a_scanned_pdf_page_goes_through_the_guard_and_a_text_page_does_not(routes):
    extractor = RoutedPdfMenuExtractor(OpenRouterMenuExtractor(ROUTE, CLOVA))
    pdfs = FIXTURES / "pdf"
    [scanned] = pdf.read_pdf((pdfs / "scanned_menu_1.pdf").read_bytes())
    [text] = pdf.read_pdf((pdfs / "text_menu_design.pdf").read_bytes())
    assert (scanned.kind, text.kind) == ("scanned", "text")

    scanned_raw = extractor.extract_page(scanned).raw_output
    text_result = extractor.extract_page(text)

    assert [row["rawText"] for row in scanned_raw["droppedEdgeRows"]] == ["하이랜드 파크 12년"]
    assert len(text_result.items) == 2 and "droppedEdgeRows" not in text_result.raw_output
    assert routes[0] is None and routes[1] is not None  # the text page's lines come from its text layer
