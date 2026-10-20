# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-20). Reviewed by Jinwoo Park.
"""Unit tests for the AI CI gate (check_test_report.py) on small JUnit and coverage fixtures."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import check_test_report as gate  # noqa: E402

POLICY = {
    "min_tests": 3,
    "allowed_skips": {"ai.ocr.test_ocr::test_live_clova_call": "needs CLOVA keys"},
    "coverage_targets": {"ai/ocr": 55, "ai/eval": 55},
}


def junit_file(tmp_path, cases):
    """cases: list of (classname, name, outcome) with outcome in passed/failed/error/skipped/xfail."""
    body = []
    for classname, name, outcome in cases:
        inner = {
            "passed": "",
            "failed": '<failure message="assert 1 == 2"/>',
            "error": '<error message="fixture error"/>',
            "skipped": '<skipped type="pytest.skip" message="CLOVA keys not set"/>',
            "xfail": '<skipped type="pytest.xfail" message="known bug"/>',
        }[outcome]
        body.append(f'<testcase classname="{classname}" name="{name}">{inner}</testcase>')
    path = tmp_path / "junit.xml"
    path.write_text(f'<testsuites><testsuite name="pytest">{"".join(body)}</testsuite></testsuites>')
    return path


PASSING = [("ai.ocr.test_ocr", "test_a", "passed"), ("ai.ocr.test_ocr", "test_b", "passed"),
           ("ai.eval.test_score", "test_c", "passed")]


def test_check_passes_when_all_tests_ran(tmp_path):
    problems, _ = gate.check(gate.read_junit(junit_file(tmp_path, PASSING)), {}, POLICY)

    assert problems == []


def test_check_fails_when_a_test_was_deleted(tmp_path):
    problems, _ = gate.check(gate.read_junit(junit_file(tmp_path, PASSING[:2])), {}, POLICY)

    assert len(problems) == 1
    assert "fewer than min_tests = 3" in problems[0]


def test_check_fails_on_failed_and_error_tests(tmp_path):
    cases = PASSING + [("ai.ocr.test_ocr", "test_d", "failed"), ("ai.ocr.test_ocr", "test_e", "error")]

    problems, _ = gate.check(gate.read_junit(junit_file(tmp_path, cases)), {}, POLICY)

    assert problems == ["2 test(s) failed: ai.ocr.test_ocr::test_d, ai.ocr.test_ocr::test_e"]


def test_check_allows_listed_skip(tmp_path):
    cases = PASSING + [("ai.ocr.test_ocr", "test_live_clova_call", "skipped")]

    problems, lines = gate.check(gate.read_junit(junit_file(tmp_path, cases)), {}, POLICY)

    assert problems == []
    assert "| `ai.ocr.test_ocr::test_live_clova_call` | CLOVA keys not set | yes |" in lines


def test_check_fails_on_unlisted_skip_or_xfail(tmp_path):
    cases = PASSING + [("ai.eval.test_score", "test_new", "skipped"), ("ai.eval.test_score", "test_old", "xfail")]

    problems, _ = gate.check(gate.read_junit(junit_file(tmp_path, cases)), {}, POLICY)

    assert [p.split(" (")[0] for p in problems] == [
        "Unexpected skip: ai.eval.test_score::test_new",
        "Unexpected skip: ai.eval.test_score::test_old",
    ]


def test_skipped_tests_do_not_count_as_passed(tmp_path):
    cases = PASSING[:2] + [("ai.ocr.test_ocr", "test_live_clova_call", "skipped")]

    problems, lines = gate.check(gate.read_junit(junit_file(tmp_path, cases)), {}, POLICY)

    assert problems == []  # 3 tests ran, the skip is allowed
    assert "Ran 3 tests: 2 passed, 0 failed, 1 skipped (minimum 3)." in lines


def test_component_coverage_combines_lines_and_branches_per_directory():
    report = {"files": {
        "ai/ocr/a.py": {"summary": {"covered_lines": 8, "num_statements": 10, "covered_branches": 1, "num_branches": 2}},
        "ai\\ocr\\b.py": {"summary": {"covered_lines": 0, "num_statements": 8, "covered_branches": 0, "num_branches": 0}},
        "ai/eval/c.py": {"summary": {"covered_lines": 5, "num_statements": 5}},
    }}

    coverage = gate.component_coverage(report, ["ai/ocr", "ai/eval", "ai/extract"])

    assert coverage == {"ai/ocr": 45.0, "ai/eval": 100.0, "ai/extract": 0.0}


def test_coverage_below_target_is_reported_not_failed(tmp_path):
    problems, lines = gate.check(gate.read_junit(junit_file(tmp_path, PASSING)),
                                 {"ai/ocr": 40.0, "ai/eval": 60.0}, POLICY)

    assert problems == []
    assert "| `ai/ocr` | 55% | 40.0% | below target |" in lines
    assert "| `ai/eval` | 55% | 60.0% | meets target |" in lines


def test_main_writes_summary_and_returns_exit_code(tmp_path, monkeypatch, capsys):
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(POLICY))
    monkeypatch.setattr(gate, "POLICY_PATH", policy_path)
    coverage_path = tmp_path / "coverage.json"
    coverage_path.write_text(json.dumps({"files": {}}))
    summary = tmp_path / "summary.md"

    ok = gate.main([str(junit_file(tmp_path, PASSING)), str(coverage_path), "--summary", str(summary)])
    failing = gate.main([str(junit_file(tmp_path, PASSING[:1])), str(coverage_path)])

    assert (ok, failing) == (0, 1)
    assert "## AI tests" in summary.read_text()
    assert "::error::Only 1 tests ran" in capsys.readouterr().out
