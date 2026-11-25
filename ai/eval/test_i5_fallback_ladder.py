"""i5_fallback_ladder.py: the pass criterion, the title check and the spending bound. No API call."""

import json

import i5_fallback_ladder as fb
import pytest

TITLE = "고든앤맥페일(Gordon&Macphail)"
LABELS = [{"raw_name": f"{TITLE} 밀튼더프 10년", "price_krw": 20000, "pour_ml": None, "unit": "glass"},
          {"raw_name": "발베니 12년", "price_krw": 18000, "pour_ml": None, "unit": "glass"}]
LINES = [{"label": f"{TITLE} 밀튼더프 10년", "price": 20000}]


def row(name, price=20000):
    return {"raw_name": name, "price_krw": price, "pour_ml": None, "unit": "glass"}


def record(rows, failures=(), cost=0.01):
    return {"rows": rows, "failures": list(failures), "cost_usd": cost, "latency_ms": 30000, "prompt_file": "p.md",
            "input_tokens": 8000, "output_tokens": 9000, "thought_tokens": 4000, "provider": "Google"}


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(fb, "PHOTOS", (("011_mirabeau_02", "regression"),))
    return tmp_path


def write(folder, run, rec):
    (folder / f"011_mirabeau_02_r{run}.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")


def test_title_of_is_the_name_up_to_the_first_closing_parenthesis():
    assert fb.title_of(f"{TITLE} 밀튼더프 10년") == TITLE


@pytest.mark.parametrize("output, attached", [
    (f"{TITLE} 밀튼더프 10년", True),
    ("고든앤맥페일 (Gordon & Macphail) 밀튼더프 10년", True),  # spaces and punctuation are not compared
    ("밀튼더프 10년", False),
    ("고든앤맥페일 밀튼더프 10년", False),  # half of the title is not the title as written
    (None, False),
])
def test_title_attached(output, attached):
    assert fb.title_attached(f"{TITLE} 밀튼더프 10년", output) is attached


def test_percentile95_is_the_index_rule_of_the_november_21_report():
    assert fb.percentile95([float(n) for n in range(1, 19)]) == 17.0
    assert fb.percentile95([5.0]) == 5.0


def test_worst_case_call_is_two_attempts_at_the_list_price():
    assert fb.worst_case_call("anthropic/claude-sonnet-5.5") == pytest.approx(2 * (30000 * 2 + 48000 * 10) / 1e6)


def test_a_model_passes_when_every_run_is_right_and_titled(folder):
    for run in fb.RUNS:
        write(folder, run, record([row(f"{TITLE} 밀튼더프 10년"), row("발베니 12년", 18000)]))
    summary = fb.summarize(folder, {"011_mirabeau_02": LABELS}, LINES, fb.RUNS)
    assert fb.verdict(summary, expected_runs=3) == {"pass": True, "reasons": []}
    assert summary["totals"]["ok"] == 6 and summary["latency"]["median_s"] == 30.0
    assert summary["cost_per_photo"] == 0.01


def test_one_run_without_the_title_fails_the_model(folder):
    for run in fb.RUNS:
        name = "밀튼더프 10년" if run == 2 else f"{TITLE} 밀튼더프 10년"
        write(folder, run, record([row(name), row("발베니 12년", 18000)]))
    summary = fb.summarize(folder, {"011_mirabeau_02": LABELS}, LINES, fb.RUNS)
    result = fb.verdict(summary, expected_runs=3)
    assert summary["totals"]["titles_missing"] == 1 and summary["totals"]["wrong"] == 0
    assert not result["pass"] and "without the title" in result["reasons"][-1]


def test_a_wrong_price_in_one_run_fails_the_model(folder):
    for run in fb.RUNS:
        write(folder, run, record([row(f"{TITLE} 밀튼더프 10년"), row("발베니 12년", 180000 if run == 3 else 18000)]))
    summary = fb.summarize(folder, {"011_mirabeau_02": LABELS}, LINES, fb.RUNS)
    assert summary["worst"]["wrong"] == 1 and summary["totals"]["kinds"]["unit_scale"] == 1
    assert not fb.verdict(summary, expected_runs=3)["pass"]


def test_a_missing_item_over_the_limit_fails_the_model(folder):
    for run in fb.RUNS:
        write(folder, run, record([row(f"{TITLE} 밀튼더프 10년")]))
    summary = fb.summarize(folder, {"011_mirabeau_02": LABELS}, LINES, fb.RUNS)
    assert summary["worst"]["missing_share"] == 0.5
    assert any("missing" in reason for reason in fb.verdict(summary, expected_runs=3)["reasons"])


def test_missing_records_and_runs_without_an_answer_fail_the_model(folder):
    cut = {"kind": "format", "detail": "status length", "cost_usd": 0.2}
    write(folder, 1, record([row(f"{TITLE} 밀튼더프 10년"), row("발베니 12년", 18000)], failures=[cut]))
    write(folder, 2, {**record(None, failures=[cut, cut], cost=None), "latency_ms": None})
    summary = fb.summarize(folder, {"011_mirabeau_02": LABELS}, LINES, fb.RUNS)
    result = fb.verdict(summary, expected_runs=3)
    assert summary["totals"]["truncated"] == 3 and summary["totals"]["failed"] == 1
    assert summary["totals"]["cost"] == pytest.approx(0.01 + 0.6)
    assert len(result["reasons"]) == 3  # 2 of 3 recorded, 1 without an answer, 1 of 3 title runs scored


def test_attempt_notes_tells_a_cut_answer_from_other_failures():
    rec = {"failures": [{"kind": "format", "detail": "status length", "cost_usd": 0.1},
                        {"kind": "format", "detail": "1 validation error", "cost_usd": 0.05},
                        {"kind": "transport", "detail": "HTTP 503"}]}
    assert fb.attempt_notes(rec) == {"truncated": 1, "format": 1, "transport": 1, "failed_cost": pytest.approx(0.15)}
