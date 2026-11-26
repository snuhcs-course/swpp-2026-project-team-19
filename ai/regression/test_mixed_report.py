"""Mixed-menu report (I4-P25): the expected lines, the metrics of one record, and the report of
the recorded prompt v1 and v2 runs, which must equal the committed ai/runs/2026-11-13_p25 files."""

import json
from pathlib import Path

import pytest

import mixed_report as mr
import regression as reg

# The report after the 2026-11-21 gold fix (잭다니엘 애플: non_whisky -> jack-daniels-apple). The report
# of ai/runs/2026-11-13_p25 is what I4 reported, made with the gold before the fix, and stays as it is.
REPORT_DIR = reg.REPO_ROOT / "ai/runs/2026-11-21_i5_not_whisky"
V1, V2 = mr.DEFAULT_RUNS


@pytest.fixture(scope="module")
def fixtures():
    return reg.load_fixtures()


@pytest.fixture(scope="module")
def report():
    return mr.build_report(list(mr.DEFAULT_RUNS))


def row(name, category="whisky", price=10000, unit="glass", pour_ml=None, note=None):
    return {"raw_name": name, "price_krw": price, "pour_ml": pour_ml, "unit": unit, "category": category, "note": note}


# ---- expected lines -------------------------------------------------------------------------

def test_expected_rows_are_the_labels_plus_the_non_whisky_lines(fixtures):
    mixed = mr.load_mixed_lines()
    rows = [r for fx in fixtures for r in mr.expected_rows(fx, mixed)]
    assert len(rows) == 472 + 70
    assert {c: sum(r["category"] == c for r in rows) for c in mr.CATEGORIES} == {
        "whisky": 462, "cocktail": 33, "food": 5, "other": 42}
    # 10 label rows are not whisky by the match gold: cognac, rum and four bottled beers
    # (11 until 2026-11-21, when 잭다니엘 애플 became a whisky line)
    from_labels = [it["raw_name"] for fx in fixtures for it in fx["expected_items"] if it["gold"] == "non_whisky"]
    assert len(from_labels) == 10 and "기네스 병" in from_labels and "헤네시 VSOP" in from_labels


def test_mixed_lines_file_is_consistent_with_the_fixtures(fixtures):
    from score import normalize

    mixed = mr.load_mixed_lines()
    by_id = {fx["photo_id"]: fx for fx in fixtures}
    assert set(mixed) <= set(by_id)
    for photo_id, lines in mixed.items():
        for line in lines:
            assert line["category"] in ("cocktail", "food", "other")
            assert line["unit"] in ("glass", "bottle", None)
            assert set(mr.ROW_KEYS) <= set(line)
            # a line of the labels is not listed twice
            assert normalize(line["raw_name"]) not in {normalize(it["raw_name"]) for it in by_id[photo_id]["expected_items"]}
    added = [line["raw_name"] for lines in mixed.values() for line in lines if line.get("added_in_review")]
    assert added == ["올드풀티니 3종 세트 / 행사", "사부로마루 피트 위스키 5종 세트 / 행사", "아르마냑 가호 5종 세트 / 행사"]


# ---- output rows ----------------------------------------------------------------------------

def test_output_rows_keep_the_category_of_non_whisky_items():
    output = {
        "items": [{"lineType": "product", "rawText": "글렌피딕 12년", "productName": "글렌피딕 12년",
                   "options": [{"optionLabel": "잔", "pourMl": 30, "priceKrw": 12000},
                               {"optionLabel": "병", "pourMl": None, "priceKrw": 150000}]},
                  {"lineType": "section_header", "rawText": "WHISKY", "options": []}],
        "otherItems": [{"rawText": "진토닉", "category": "cocktail",
                        "options": [{"optionLabel": "잔", "pourMl": None, "priceKrw": 9000}]},
                       {"rawText": "오늘의 안주", "category": "food", "options": []}],
    }
    rows = mr.output_rows(output)
    assert [(r["raw_name"], r["category"], r["unit"], r["price_krw"]) for r in rows] == [
        ("글렌피딕 12년", "whisky", "glass", 12000), ("글렌피딕 12년", "whisky", "bottle", 150000),
        ("진토닉", "cocktail", "glass", 9000), ("오늘의 안주", "food", None, None)]
    assert mr.output_rows(None) == []  # an answer the server rejects


# ---- one record -----------------------------------------------------------------------------

def test_a_perfect_record_has_no_error():
    expected = [row("글렌피딕 12년"), row("진토닉", "cocktail"), row("감자튀김", "food")]
    score = mr.score_record(expected, [dict(r) for r in expected])
    c = score["counts"]
    assert (c["expected"], c["paired"], c["extra"], c["priced"], c["price_correct"], c["duplicates"]) == (3, 3, 0, 3, 3, 0)
    assert (c["expected_whisky"], c["expected_non_whisky"], c["paired_whisky"], c["paired_non_whisky"]) == (1, 2, 1, 2)
    assert score["errors"] == [] and score["missed"] == []
    assert mr.rates(c) == {"line_recall": 1.0, "whisky_line_recall": 1.0, "non_whisky_line_recall": 1.0,
                           "extra_line_rate": 0.0, "price_accuracy": 1.0, "duplicate_line_rate": 0.0,
                           "classification_error_rate": 0.0}


def test_the_three_classification_errors_are_told_apart():
    expected = [row("글렌피딕 12년"), row("헤네시 VSOP", "other"), row("진토닉", "cocktail"), row("교자", "food")]
    out = [row("글렌피딕 12년", "other"), row("헤네시 VSOP", "whisky"), row("진토닉", "food"), row("교자", "food")]
    score = mr.score_record(expected, out)
    c = score["counts"]
    assert (c["whisky_as_non_whisky"], c["non_whisky_as_whisky"], c["wrong_kind"]) == (1, 1, 1)
    assert mr.rates(c)["classification_error_rate"] == 0.75
    assert {(e["line"], e["type"]) for e in score["errors"]} == {
        ("글렌피딕 12년", "whisky_as_non_whisky"), ("헤네시 VSOP", "non_whisky_as_whisky"), ("진토닉", "wrong_kind")}
    assert score["confusion"] == {"whisky->other": 1, "other->whisky": 1, "cocktail->food": 1, "food->food": 1}


def test_missed_extra_duplicate_and_price():
    expected = [row("글렌피딕 12년"), row("맥캘란 12년", price=20000), row("진토닉", "cocktail"),
                row("시가", "other", price=30000, note="시가")]
    out = [row("글렌피딕 12년"), row("글렌피딕 12년"), row("맥캘란 12년", price=200000), row("없는 술"),
           row("시가", "other", price=1)]
    score = mr.score_record(expected, out)
    c = score["counts"]
    assert (c["paired"], c["extra"], c["duplicates"]) == (3, 2, 1)
    assert (c["priced"], c["price_correct"]) == (2, 1)  # a row with a price note is not price-checked
    assert score["missed"] == [{"line": "진토닉", "expected": "cocktail"}]
    r = mr.rates(c)
    assert (r["line_recall"], r["extra_line_rate"], r["duplicate_line_rate"], r["price_accuracy"]) == (0.75, 0.4, 0.2, 0.5)


def test_an_empty_or_rejected_record():
    score = mr.score_record([row("글렌피딕 12년")], [], rejected=True)
    assert score["counts"]["rejected"] == 1 and score["counts"]["paired"] == 0
    r = mr.rates(score["counts"])
    assert r["line_recall"] == 0.0 and r["extra_line_rate"] is None and r["price_accuracy"] is None
    assert r["non_whisky_line_recall"] is None  # the photo has no non-whisky line


# ---- the recorded runs ----------------------------------------------------------------------

def test_report_of_the_recorded_runs_equals_the_committed_report(report):
    assert json.loads((REPORT_DIR / "mixed_report.json").read_text(encoding="utf-8")) == json.loads(reg.dump_json(report))
    assert (REPORT_DIR / "mixed_report.md").read_text(encoding="utf-8") == mr.markdown(report) + "\n"


def test_headline_numbers_of_the_recorded_runs(report):
    assert report["fixtures"]["photos"] == 15 and report["fixtures"]["expected_rows"] == 542
    v1, v2 = report["runs"][V1], report["runs"][V2]
    for run in (v1, v2):
        assert run["counts"]["records"] == 45 and run["counts"]["rejected"] == 0
        assert run["counts"]["expected"] == 3 * 542 and list(run["per_run"]) == ["1", "2", "3"]
        assert run["photos_without_record"] == [] and len(run["per_photo"]) == 15
        assert run["counts"]["duplicates"] == 0 and run["counts"]["whisky_as_non_whisky"] == 0
        assert sum(r["counts"]["paired"] for r in run["per_run"].values()) == run["counts"]["paired"]
        assert sum(p["counts"]["paired"] for p in run["per_photo"].values()) == run["counts"]["paired"]
    # prompt v1 has no categories: a non-whisky line it returns is a whisky line to the server
    assert (v1["counts"]["paired_non_whisky"], v1["counts"]["non_whisky_as_whisky"]) == (58, 58)
    assert v1["rates"]["non_whisky_line_recall"] == 0.2417
    # prompt v2 keeps the non-whisky lines; what is left are the lines inside whisky lists
    assert (v2["counts"]["paired_non_whisky"], v2["counts"]["expected_non_whisky"]) == (231, 240)
    assert v2["counts"]["non_whisky_as_whisky"] == 17 and v2["counts"]["wrong_kind"] == 0
    assert {e["line"] for e in v2["misclassified"]} == {
        "헤네시vsop / Hennessy vsop", "레미마틴vsop / Remy Martin vsop", "김과장 #2 (바베이도스 럼)",
        "헤네시 VSOP"}
    # the three set lines found in review are missing from every v2 record
    sets = [e for e in v2["missed"] if "세트" in e["line"]]
    assert len(sets) == 9 and {e["photo_id"] for e in sets} == {"009_오드비_09"}


def test_markdown_has_one_table_per_run_directory_and_groups_long_lists(report):
    text = mr.markdown(report)
    assert text.count("| Line recall |") == 2 and f"## {V1}" in text and f"## {V2}" in text
    assert "| | all runs | r1 | r2 | r3 |" in text
    assert "- 007_위스키복춘_04: 33 lines (cocktail; 3)" in text  # the cocktail page prompt v1 leaves out
    assert "- 009_오드비_09: 올드풀티니 3종 세트 / 행사 (other; 3)" in text


# ---- command --------------------------------------------------------------------------------

def test_command_writes_json_and_markdown(tmp_path, capsys):
    out_json, out_md = tmp_path / "r.json", tmp_path / "r.md"
    assert mr.main([V2, "--json", str(out_json), "--markdown", str(out_md)]) == 0
    printed = capsys.readouterr().out
    written = json.loads(out_json.read_text(encoding="utf-8"))
    assert list(written["runs"]) == [V2] and written["runs"][V2]["counts"]["records"] == 45
    assert out_md.read_text(encoding="utf-8") == printed
    assert "# Mixed-menu extraction report" in printed


def test_command_on_a_directory_without_records_and_on_a_missing_one(tmp_path, capsys):
    assert mr.main([str(tmp_path)]) == 0
    printed = capsys.readouterr().out
    assert "No record for: 007_위스키복춘_01" in printed and "| Line recall | - (0/0) |" in printed
    assert mr.main([str(tmp_path / "nope")]) == 2
    assert "not a directory" in capsys.readouterr().out


def test_a_record_of_another_photo_with_the_same_prefix_is_not_read(tmp_path, fixtures):
    fx = fixtures[0]
    stem = Path(fx["photo"]["file"]).stem
    (tmp_path / f"{stem}_extra_r1.json").write_text("{}", encoding="utf-8")
    run = mr.report_run_dir(tmp_path, [fx], {})
    assert run["counts"]["records"] == 0 and run["photos_without_record"] == [fx["photo_id"]]
