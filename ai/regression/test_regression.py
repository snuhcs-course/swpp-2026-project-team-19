"""The 15-photo regression check (regression.py) and the checker itself."""

import hashlib
import json

import pytest
import regression as reg

FIXTURES = reg.load_fixtures()
BASELINE = json.loads(reg.BASELINE.read_text(encoding="utf-8"))
NOW_EXTRACTION = reg.replay(FIXTURES)
NOW_MATCHING = reg.match_lines(FIXTURES)


# ---- the fixtures ---------------------------------------------------------------------------

def test_fixtures_follow_selection_labels_and_gold():
    assert FIXTURES == reg.build_fixtures(), "fixtures/ is stale: run regression.py --update"


def test_fixture_set_covers_the_failure_kinds():
    assert len(FIXTURES) == 15
    assert len({fx["bar"] for fx in FIXTURES}) == 5
    why = {w for fx in FIXTURES for w in fx["why"]}
    assert {"omission", "extra_lines", "wrong_match", "price", "pour_size", "glass_bottle_confusion",
            "non_whisky_page", "non_whisky_lines"} <= why
    assert sum(len(fx["expected_items"]) for fx in FIXTURES) == 472
    assert any(i["pour_ml"] for fx in FIXTURES for i in fx["expected_items"])
    assert {i["unit"] for fx in FIXTURES for i in fx["expected_items"]} == {"glass", "bottle"}
    for fx in FIXTURES:
        assert len(fx["photo"]["sha256"]) == 64 and fx["history"]


def test_no_fixture_comes_from_the_frozen_i3_set_or_an_inactive_bar():
    for fx in FIXTURES:
        assert "i3" not in fx["labels"] and "i3" not in fx["gold"]
        assert fx["bar"] not in ("Beck", "포레스트")


# ---- extraction replay ----------------------------------------------------------------------

def test_every_fixture_has_a_recorded_answer():
    assert {r["photo_id"] for r in NOW_EXTRACTION.values()} == {fx["photo_id"] for fx in FIXTURES}
    assert sorted(NOW_EXTRACTION) == sorted(BASELINE["extraction"])


@pytest.mark.parametrize("record", sorted(BASELINE["extraction"]))
def test_extraction_replay_equals_baseline(record):
    assert NOW_EXTRACTION[record] == BASELINE["extraction"][record]


def test_replay_notices_a_change_in_glass_and_bottle_grouping(monkeypatch):
    import app.extraction.convert as convert
    monkeypatch.setattr(convert, "group_items", lambda items: [[i] for i in items])
    record = next(k for k, v in BASELINE["extraction"].items() if v["photo_id"] == "007_위스키복춘_01")
    now = reg.replay([fx for fx in FIXTURES if fx["photo_id"] == "007_위스키복춘_01"])[record]
    assert now["flow_items"] == 77 != BASELINE["extraction"][record]["flow_items"] == 39
    assert now["correct"] == BASELINE["extraction"][record]["correct"]


def test_replay_keeps_the_known_failures_visible():
    by_photo = {}
    for r in BASELINE["extraction"].values():
        by_photo.setdefault(r["photo_id"], []).append(r)
    assert sum(r["fp"] for r in by_photo["010_수이_04"]) == 12       # other spirits returned as whisky
    assert sum(r["fn"] for r in by_photo["009_오드비_09"]) == 4        # bottled beers left out
    assert sum(r["fp"] for r in by_photo["007_위스키복춘_04"]) == 2     # cocktails on a cocktail-only page
    assert sum(r["unit_confusion"] for r in by_photo["011_미라보_07"]) == 1
    assert sum(r["priced"] - r["price_correct"] for r in by_photo["007_위스키복춘_01"]) == 1
    assert not any(r["rejected"] for r in BASELINE["extraction"].values())


# ---- matching -------------------------------------------------------------------------------

@pytest.mark.parametrize("condition", reg.CONDITIONS)
def test_matching_is_not_worse_than_baseline(condition):
    worse, _ = reg.compare_matching({condition: BASELINE["matching"][condition]}, NOW_MATCHING)
    assert not worse, "\n".join(worse)


def test_deployed_catalog_resolves_every_known_line_without_a_false_merge():
    rows = [r for rows in NOW_MATCHING["deployed"].values() for r in rows]
    counts = reg.matching_counts(rows)
    assert counts["known_correct"] == counts["known"] > 300
    assert counts["false_merge"] == 0
    assert reg.matching_counts([r for rows in NOW_MATCHING["heldout"].values() for r in rows])["false_merge"] == 0


# ---- the checker ----------------------------------------------------------------------------

def row(outcome, kind="known", name="맥캘란 12", rank1="macallan-12"):
    return {"name": name, "gold": "macallan-12", "kind": kind, "outcome": outcome, "status": "x", "rank1": rank1}


@pytest.mark.parametrize("before, after", [("correct", "unmatched"), ("correct", "ambiguous_ok"),
                                           ("ambiguous_ok", "ambiguous_bad"), ("unmatched", "false_merge")])
def test_compare_matching_reports_a_line_that_got_worse(before, after):
    worse, better = reg.compare_matching({"deployed": {"p": [row(before)]}}, {"deployed": {"p": [row(after)]}})
    assert len(worse) == 1 and before in worse[0] and after in worse[0] and not better


def test_compare_matching_lets_an_improvement_through():
    worse, better = reg.compare_matching({"deployed": {"p": [row("unmatched")]}}, {"deployed": {"p": [row("correct")]}})
    assert not worse and len(better) == 1


def test_compare_matching_reports_changed_lines_and_a_missing_photo():
    base = {"deployed": {"p": [row("correct")], "q": [row("correct")]}}
    worse, _ = reg.compare_matching(base, {"deployed": {"p": [row("correct", name="다른 줄")]}})
    assert len(worse) == 2


def test_unmatched_is_right_for_a_product_the_catalog_lacks():
    assert reg.severity(row("unmatched", kind="absent")) == 0
    assert reg.severity(row("unmatched", kind="non_whisky")) == 0
    assert reg.severity(row("unmatched")) == 2
    assert reg.severity(row("false_merge", kind="absent")) == 4


def test_flatten_gives_one_row_per_option_and_skips_other_line_types():
    flow = [
        {"lineType": "product", "rawText": "A", "options": [
            {"optionLabel": "잔", "pourMl": 30, "priceKrw": 9000}, {"optionLabel": "병", "pourMl": None, "priceKrw": 90000}]},
        {"lineType": "product", "rawText": "B", "options": []},
        {"lineType": "section_header", "rawText": "WHISKY", "options": []},
    ]
    assert reg.flatten(flow) == [
        {"raw_name": "A", "price_krw": 9000, "pour_ml": 30, "unit": "glass"},
        {"raw_name": "A", "price_krw": 90000, "pour_ml": None, "unit": "bottle"},
        {"raw_name": "B", "price_krw": None, "pour_ml": None, "unit": None},
    ]


def test_duplicates_counts_repeated_rows_only():
    a = {"raw_name": "A 12", "price_krw": 9000, "pour_ml": None, "unit": "glass"}
    assert reg.duplicates([a, {**a, "raw_name": "a  12"}, {**a, "unit": "bottle"}, {**a, "price_krw": 1}]) == 1


def test_server_items_groups_a_glass_and_bottle_pair_and_record_rows_handles_a_rejected_answer():
    item = {"raw_name": "A", "price_krw": 9000, "pour_ml": None, "unit": "glass", "source_lines": {"name": [], "price": []}}
    text = json.dumps({"items": [item, {**item, "unit": "bottle", "price_krw": 90000}]})
    assert [len(i["options"]) for i in reg.server_items(text)] == [2]
    assert len(reg.flatten(reg.record_items({"raw_text": text}))) == 2
    assert reg.record_items({"raw_text": "not json"}) is None
    assert reg.record_items({"raw_text": json.dumps({"items": [{**item, "price_krw": -1}]})}) is None
    assert reg.record_items({}) is None


def test_check_passes_on_the_baseline_and_reports_a_changed_score(capsys):
    assert reg.check(BASELINE, FIXTURES) == ([], [])
    changed = json.loads(json.dumps(BASELINE))
    record = sorted(changed["extraction"])[0]
    changed["extraction"][record]["fn"] += 1
    del changed["extraction"][sorted(changed["extraction"])[1]]
    problems, _ = reg.check(changed, FIXTURES)
    assert len(problems) == 2 and "fn" in problems[0] and "missing" in problems[1]
    assert reg.main([]) == 0
    assert "REGRESSION" not in capsys.readouterr().out


def test_main_scores_a_new_run_directory(capsys):
    assert reg.main(["--extraction", str(reg.REPO_ROOT / "ai/runs/2026-10-17_p47/hybrid_final_v1"), "--run", "1"]) == 0
    out = capsys.readouterr().out
    assert "010_sui_04_r1.json" in out and "extra 12" in out and "no record for:" in out and "007_위스키복춘_01" in out


def test_check_photos_compares_hashes(tmp_path, capsys):
    fx = json.loads(json.dumps(FIXTURES[:2]))
    for f, body in zip(fx, (b"photo-0", b"photo-1")):
        path = tmp_path / f["photo"]["photo_dir"] / f["photo"]["file"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        f["photo"]["sha256"] = hashlib.sha256(body).hexdigest()
    assert reg.check_photos(tmp_path, fx) == []
    (tmp_path / fx[0]["photo"]["photo_dir"] / fx[0]["photo"]["file"]).write_bytes(b"other")
    (tmp_path / fx[1]["photo"]["photo_dir"] / fx[1]["photo"]["file"]).unlink()
    problems = reg.check_photos(tmp_path, fx)
    assert len(problems) == 2 and "SHA-256" in problems[0] and "missing" in problems[1]
    assert reg.main(["--check-photos", str(tmp_path)]) == 1
    assert "missing" in capsys.readouterr().out


def test_update_rewrites_the_same_files(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(reg, "FIXTURE_DIR", tmp_path / "fixtures")
    monkeypatch.setattr(reg, "BASELINE", reg.REPO_ROOT / "ai" / "regression" / "baseline.tmp.json")
    try:
        assert reg.main(["--update"]) == 0
        assert json.loads(reg.BASELINE.read_text(encoding="utf-8")) == BASELINE
        assert len(list((tmp_path / "fixtures").glob("*.json"))) == 15
    finally:
        reg.BASELINE.unlink(missing_ok=True)


def test_a_known_product_that_leaves_the_catalog_is_a_regression():
    # known/correct and absent/unmatched have the same severity; the kind change must still fail
    before = {"deployed": {"p": [{"name": "A 12", "gold": "a-12", "kind": "known", "outcome": "correct", "rank1": "a-12"}]}}
    after = {"deployed": {"p": [{"name": "A 12", "gold": "a-12", "kind": "absent", "outcome": "unmatched", "rank1": None}]}}
    assert reg.severity(before["deployed"]["p"][0]) == reg.severity(after["deployed"]["p"][0])
    worse, better = reg.compare_matching(before, after)
    assert len(worse) == 1 and "was known and is absent now" in worse[0] and not better


def test_removing_a_product_from_the_catalog_fails_the_matching_check():
    seed = reg.load_seed()
    fx = FIXTURES[0]
    gone = next(i["gold"] for i in fx["expected_items"] if i["gold"] in {p["key"] for p in seed["products"]})
    smaller = {**seed, "products": [p for p in seed["products"] if p["key"] != gone]}
    now = reg.match_lines([fx], smaller)
    worse, _ = reg.compare_matching({c: {fx["photo_id"]: BASELINE["matching"][c][fx["photo_id"]]} for c in reg.CONDITIONS}, now)
    assert len(worse) >= 2 and all("was known and is absent now" in line and gone in line for line in worse)


def test_replay_compares_pour_sizes():
    fx = next(f for f in FIXTURES if any(i["pour_ml"] for i in f["expected_items"]))
    rows = [{k: i[k] for k in ("raw_name", "price_krw", "pour_ml", "unit")} for i in fx["expected_items"]]
    assert reg.score_rows(fx, rows)["pour_wrong"] == 0
    target = next(r for r in rows if r["pour_ml"])
    target["pour_ml"] *= 2
    score = reg.score_rows(fx, rows)
    assert score["pour_wrong"] == 1 and score["correct"] == len(rows)  # score.py alone sees nothing
    assert [e["type"] for e in score["errors"]] == ["pour size"]
    # a pour size the menu does not print must not be made up either
    fx = next(f for f in FIXTURES if any(i["pour_ml"] is None for i in f["expected_items"]))
    rows = [{k: i[k] for k in ("raw_name", "price_krw", "pour_ml", "unit")} for i in fx["expected_items"]]
    next(r for r in rows if r["pour_ml"] is None)["pour_ml"] = 30
    assert reg.score_rows(fx, rows)["pour_wrong"] == 1
