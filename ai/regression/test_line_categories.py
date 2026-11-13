"""I4-P12: with prompt v2 the non-whisky lines of a menu never reach product matching.

Prompt v2 answers are not recorded yet, so these tests take the recorded prompt v1 answers of the
regression photos and add the category a v2 answer carries (`as_v2`). The names, prices and source
lines are the model's own; only the category is set here.
"""

import json

import pytest
import regression as reg

FIXTURES = {fx["photo_id"]: fx for fx in reg.load_fixtures()}
BASELINE = json.loads(reg.BASELINE.read_text(encoding="utf-8"))
SUI_04 = "ai/runs/2026-10-17_p47/hybrid_final_v1/010_sui_04_r1.json"
SUI_02 = "ai/runs/2026-10-17_p47/hybrid_final_v1/010_sui_02_r1.json"
BOKCHUN_04 = "ai/runs/2026-10-14_e2e/hybrid_val_v1/007_bokchun_04_r1.json"


def as_v2(record_path: str, categories: dict[str, str], extra: list[dict] = ()) -> dict:
    """The recorded answer as a prompt v2 record: `categories` maps a raw_name to its category
    (every other line is whisky); `extra` rows are appended."""
    record = reg.read_json(record_path)
    items = json.loads(record["raw_text"])["items"]
    for item in items:
        item["category"] = categories.get(item["raw_name"], "whisky")
    return {"prompt_version": "hybrid-v2", "raw_text": json.dumps({"items": items + list(extra)}, ensure_ascii=False)}


def row(name, category, price=15000, unit="glass", pour=None):
    return {"raw_name": name, "price_krw": price, "pour_ml": pour, "unit": unit,
            "source_lines": {"name": [], "price": []}, "category": category}


def extra_lines(record_path: str) -> list[str]:
    """Names the recorded v1 run returned that the label leaves out."""
    return [e["got"] for e in BASELINE["extraction"][record_path]["errors"] if e["expected"] is None]


@pytest.fixture(scope="module")
def sui():
    """수이's catalog as deployed, with a matcher that records every name it is asked to resolve."""
    be = reg.harness.Backend(reg.REPO_ROOT)
    catalog = reg.harness.build_catalog(be, "", "service", reg.load_seed()).catalog
    asked = []
    resolve = be.resolve
    be.resolve = lambda name, cat: (asked.append(name), resolve(name, cat))[1]
    return be, catalog, asked


def test_other_spirits_next_to_whisky_do_not_reach_the_matcher(sui):
    be, catalog, asked = sui
    asked.clear()
    others = extra_lines(SUI_04)
    assert len(others) == 12 and "Hennesy X.O" in others            # tequila, cognac, calvados
    output = reg.server_output(as_v2(SUI_04, dict.fromkeys(others, "other")))
    results = reg.match_items(be, output["items"], catalog)
    assert len(asked) == len(results) == 28 and not set(asked) & set(others)
    assert [o["rawText"] for o in output["otherItems"]] == others
    assert all(o["category"] == "other" and o["options"][0]["priceKrw"] for o in output["otherItems"])


def test_the_whisky_lines_of_that_menu_score_and_match_as_before():
    fx = FIXTURES["010_수이_04"]
    v1 = BASELINE["extraction"][SUI_04]
    output = reg.server_output(as_v2(SUI_04, dict.fromkeys(extra_lines(SUI_04), "other")))
    score = reg.score_rows(fx, reg.flatten(output["items"]))
    assert (v1["fp"], score["fp"]) == (12, 0)                         # the 12 extra lines are gone
    assert score["correct"] == v1["correct"] == 28 and score["fn"] == 0
    assert score["priced"] == score["price_correct"] == v1["price_correct"]


def test_a_cocktail_spelled_like_a_catalog_whisky_is_not_matched(sui):
    be, catalog, asked = sui
    name = "Macallan 12y Sherry Cask (쉐리)"                          # a whisky line of 수이_02
    assert be.resolve(name, catalog).status == "exact_match"          # as whisky it is confirmed at once
    asked.clear()
    output = reg.server_output({"prompt_version": "hybrid-v2", "raw_text": json.dumps(
        {"items": [row(name, "cocktail", 18000), row("Glenfiddich 12 Highball", "cocktail", 12000)]})})
    assert reg.match_items(be, output["items"], catalog) == [] and asked == []
    assert [(o["rawText"], o["category"]) for o in output["otherItems"]] == [
        (name, "cocktail"), ("Glenfiddich 12 Highball", "cocktail")]


def test_food_and_drinks_keep_price_and_pour_size_without_matching(sui):
    be, catalog, asked = sui
    asked.clear()
    extra = [row("치즈 플래터", "food", 25000, None), row("하우스 와인", "other", 9000, "glass", 120),
             row("하우스 와인", "other", 45000, "bottle"), row("기네스 병", "other", 12000, "bottle", 330)]
    output = reg.server_output(as_v2(SUI_02, {}, extra))
    reg.match_items(be, output["items"], catalog)
    assert not {"치즈 플래터", "하우스 와인", "기네스 병"} & set(asked) and len(asked) == len(output["items"])
    food, wine, beer = output["otherItems"]
    assert food["options"] == [{"optionLabel": None, "pourMl": None, "priceKrw": 25000}]
    assert wine["options"] == [{"optionLabel": "잔", "pourMl": 120, "priceKrw": 9000},
                               {"optionLabel": "병", "pourMl": None, "priceKrw": 45000}]
    assert beer["options"] == [{"optionLabel": "병", "pourMl": 330, "priceKrw": 12000}]


def test_a_cocktail_only_page_sends_nothing_to_the_matcher(sui):
    be, catalog, asked = sui
    asked.clear()
    cocktails = extra_lines(BOKCHUN_04)
    assert cocktails == ["복춘", "입춘"] and BASELINE["extraction"][BOKCHUN_04]["fp"] == 2
    output = reg.server_output(as_v2(BOKCHUN_04, dict.fromkeys(cocktails, "cocktail")))
    assert output["items"] == [] and reg.match_items(be, output["items"], catalog) == [] and asked == []
    assert [(o["rawText"], o["options"][0]["priceKrw"]) for o in output["otherItems"]] == [("복춘", 15000), ("입춘", 18000)]
    assert reg.score_rows(FIXTURES["007_위스키복춘_04"], reg.flatten(output["items"]))["fp"] == 0


def test_a_line_tagged_whisky_still_goes_to_the_matcher(sui):
    # The category decides, not the name: a cognac under a whisky heading stays a whisky line (prompt v2
    # "이름만 보고 종류를 판단하지 않는다"), so it is matched and, with no catalog product, left for the owner.
    be, catalog, asked = sui
    asked.clear()
    output = reg.server_output({"prompt_version": "hybrid-v2",
                                "raw_text": json.dumps({"items": [row("Hennesy X.O", "whisky", 42000)]})})
    results = reg.match_items(be, output["items"], catalog)
    assert asked == ["Hennesy X.O"] and results[0][1].status != "exact_match" and output["otherItems"] == []


def test_a_v1_record_has_no_other_items_and_a_v2_record_without_category_is_rejected():
    assert reg.server_output(reg.read_json(SUI_04))["otherItems"] == []
    record = reg.read_json(SUI_04)
    assert reg.record_output({"prompt_version": "hybrid-v2", "raw_text": record["raw_text"]}) is None


def test_scoring_a_v2_run_directory_reports_the_other_lines(tmp_path, capsys):
    record = as_v2(SUI_04, dict.fromkeys(extra_lines(SUI_04), "other"))
    (tmp_path / "010_sui_04_r1.json").write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    assert reg.main(["--extraction", str(tmp_path)]) == 0
    line = next(x for x in capsys.readouterr().out.splitlines() if "010_sui_04_r1.json" in x)
    assert "extra  0" in line and "other 12" in line and "correct  28/28" in line
