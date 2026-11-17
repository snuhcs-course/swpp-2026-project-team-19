"""p46_report.py on made-up labels, records and matching results (never the I3 photos or runs)."""

import json

import p46_report as p46
import pytest

LABELS = {"photos": [{"photo_id": "t_01", "bar": "바", "items": [
    {"raw_name": "페른홀로우 12년", "price_krw": 15000, "pour_ml": None, "unit": "glass", "note": None},
    {"raw_name": "헤네시 VSOP", "price_krw": 20000, "pour_ml": None, "unit": "glass", "note": None}]}]}
GOLD = {"photos": [{"photo_id": "t_01", "bar": "바", "items": [
    {"raw_name": "페른홀로우 12년", "gold": "fernhollow-12"}, {"raw_name": "헤네시 VSOP", "gold": "non_whisky"}]}]}
HASHES = {"photos": [{"photo_id": "t_01", "file": "t_01.jpg", "sha256": "0"}]}
LINES = {"t_01": [{"raw_name": "모히토", "category": "cocktail", "price_krw": 12000, "pour_ml": None, "unit": "glass"}]}


def model_item(name, price, category=None):
    item = {"raw_name": name, "price_krw": price, "pour_ml": None, "unit": "glass",
            "source_lines": {"name": [], "price": []}}
    return {**item, "category": category} if category else item


def test_fixtures_pair_the_labels_with_the_gold():
    [fx] = p46.i3_fixtures(LABELS, GOLD, HASHES)
    assert fx["photo"]["file"] == "t_01.jpg" and [i["gold"] for i in fx["expected_items"]] == ["fernhollow-12", "non_whisky"]
    other = {"photos": [{**GOLD["photos"][0], "items": GOLD["photos"][0]["items"][::-1]}]}
    with pytest.raises(SystemExit, match="gold names differ"):
        p46.i3_fixtures(LABELS, other, HASHES)


def test_mixed_report_scores_v2_records_and_replays_p30_records(tmp_path):
    fixtures = p46.i3_fixtures(LABELS, GOLD, HASHES)
    v2 = tmp_path / "v2"
    v2.mkdir()
    answer = {"items": [model_item("페른홀로우 12년", 15000, "whisky"), model_item("헤네시 VSOP", 20000, "whisky"),
                        model_item("모히토", 12000, "cocktail")]}
    (v2 / "t_01_r1.json").write_text(json.dumps(
        {"prompt_version": "hybrid-v2", "raw_text": json.dumps(answer, ensure_ascii=False), "ocr_lines": []},
        ensure_ascii=False), encoding="utf-8")
    report = p46.mixed_report(v2, fixtures, LINES)
    counts = report["counts"]
    assert (counts["expected_whisky"], counts["expected_non_whisky"], counts["paired_non_whisky"]) == (1, 2, 2)
    assert counts["non_whisky_as_whisky"] == 1 and counts["whisky_as_non_whisky"] == 0
    assert [e["line"] for e in report["misclassified"]] == ["헤네시 VSOP"] and report["missed_non_whisky"] == []
    # a P30 record: prompt v1, the model output without its text, and no cocktail line in it
    v1 = tmp_path / "v1"
    v1.mkdir()
    output = {"items": [model_item("페른홀로우 12년", 15000), model_item("헤네시 VSOP", 20000)]}
    (v1 / "t_01_r1.json").write_text(json.dumps({"prompt_version": "hybrid-v1", "output": output}, ensure_ascii=False),
                                     encoding="utf-8")
    (v1 / "t_01_r2.json").write_text(json.dumps({"prompt_version": "hybrid-v1", "output": None}), encoding="utf-8")
    old = p46.mixed_report(v1, fixtures, LINES)
    assert old["records"] == 2 and old["counts"]["rejected"] == 1
    assert old["per_run"]["1"]["counts"]["non_whisky_as_whisky"] == 1
    assert {e["line"] for e in old["missed_non_whisky"]} == {"모히토", "헤네시 VSOP"}


def matching_result(catalog, top1, *, llm=None, server=None, extraction=False, complete=True):
    block = lambda t: {"all": {"lines": 10, "top1": t, "fm_rate": 0.0, "accept_err_rate": 0.01, "hard_per_photo": 2.0}}
    result = {"catalog": catalog, "input": "extraction x r1" if extraction else "label", "catalog_digest": "d",
              "rules_repo_head": "abc", "rules": block(top1)}
    if llm is not None:
        result["llm"] = {**block(llm), "complete": complete}
    if server is not None:
        result["server"] = {**block(server), "complete": complete, "after": "llm" if llm is not None else "rules"}
    return result


def test_matching_results_are_grouped_and_incomplete_runs_left_out(tmp_path):
    files = {"a.json": matching_result("full", 0.7, llm=0.7, server=0.7),
             "b.json": matching_result("full", 0.7, llm=0.8, server=0.8),
             "c.json": matching_result("full", 0.7, llm=0.9, complete=False),
             "d.json": matching_result("ops", 0.6, extraction=True)}
    for name, result in files.items():
        (tmp_path / name).write_text(json.dumps(result), encoding="utf-8")
    grouped = p46.matching_groups([tmp_path / name for name in files])
    groups = grouped["groups"]
    assert set(groups) == {"full/label/rules", "full/label/llm", "full/label/server after llm", "ops/e2e/rules"}
    assert groups["full/label/llm"]["top1"] == {"mean": 0.75, "min": 0.7, "max": 0.8, "n": 2}
    assert groups["full/label/rules"]["top1"]["n"] == 3
    assert grouped["incomplete_left_out"] == ["c.json:llm"]


def test_the_table_says_which_thresholds_are_met(tmp_path, monkeypatch):
    for rel, data in ((p46.LABELS, LABELS), (p46.GOLD, GOLD), (p46.PHOTO_HASHES, HASHES),
                      (p46.MIXED_LINES, {"reviewed": None, "photos": LINES})):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    run_dir = tmp_path / "v2"
    run_dir.mkdir()
    spread = lambda v: {"mean": v, "min": v, "max": v, "n": 3}
    (run_dir / "scores.json").write_text(json.dumps({"failed_calls": [], "summary": {
        "f1_strict": spread(0.95), "price_accuracy": spread(0.94), "item_accuracy": spread(0.9)}}), encoding="utf-8")
    match = tmp_path / "m.json"
    match.write_text(json.dumps(matching_result("full", 0.774)), encoding="utf-8")
    report = p46.build({"v2": run_dir}, [match], repo=tmp_path)
    assert report["expected_rows"] == {"whisky": 1, "cocktail": 1, "food": 0, "other": 1}
    text = p46.markdown(report)
    assert "0.950 [0.950-0.950] (NFR-1 >= 0.9: met)" in text and "0.940 [0.940-0.940] (NFR-2 >= 0.95: NOT met)" in text
    assert "| full/label/rules | 0.774 (NFR-3 >= 0.9: NOT met) | 0.0000 (NFR-4 <= 0.02: met)" in text
    assert p46.verdict("hard_per_photo", 1.0) == "" and p46._cell(None) == "-"


def test_the_i3_non_whisky_lines_file_has_the_fields_the_report_reads():
    lines = json.loads((p46.REPO_ROOT / p46.MIXED_LINES).read_text(encoding="utf-8"))
    labels = json.loads((p46.REPO_ROOT / p46.LABELS).read_text(encoding="utf-8"))
    photo_ids = {p["photo_id"] for p in labels["photos"]}
    rows = [row for photo_id, photo in lines["photos"].items() for row in photo if photo_id in photo_ids]
    assert len(rows) == sum(len(photo) for photo in lines["photos"].values()) == 14
    assert all(set(row) == {"raw_name", "category", "price_krw", "pour_ml", "unit"} for row in rows)
    assert {row["category"] for row in rows} <= {"cocktail", "food", "other"}


def test_main_writes_the_json_and_the_table(tmp_path, capsys):
    match = tmp_path / "m.json"
    match.write_text(json.dumps(matching_result("asis", 0.8)), encoding="utf-8")
    assert p46.main(["--out", str(tmp_path / "out"), "--matching", str(match)]) == 0
    assert json.loads((tmp_path / "out" / "p46_metrics.json").read_text(encoding="utf-8"))["matching"]["groups"]
    assert "asis/label/rules" in (tmp_path / "out" / "p46_metrics.md").read_text(encoding="utf-8")
    with pytest.raises(SystemExit):
        p46.main(["--out", str(tmp_path / "out"), "--extraction", "v2=" + str(tmp_path / "nowhere")])
