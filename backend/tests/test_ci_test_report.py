"""Unit tests for the backend CI gate (ci/check_test_report.py) on small JUnit and collect-only fixtures."""

import json

from ci import check_test_report as gate

POLICY = {
    "min_tests": 3,
    "allowed_skips": {"tests.test_seed::test_live_seed": "needs the seed files"},
}


def junit_file(tmp_path, cases):
    """cases: list of (classname, name, outcome) with outcome in passed/failed/error/skipped/xfail."""
    body = []
    for classname, name, outcome in cases:
        inner = {
            "passed": "",
            "failed": '<failure message="assert 1 == 2"/>',
            "error": '<error message="fixture error"/>',
            "skipped": '<skipped type="pytest.skip" message="seed files missing"/>',
            "xfail": '<skipped type="pytest.xfail" message="known bug"/>',
        }[outcome]
        body.append(f'<testcase classname="{classname}" name="{name}">{inner}</testcase>')
    path = tmp_path / "junit.xml"
    path.write_text(f'<testsuites><testsuite name="pytest">{"".join(body)}</testsuite></testsuites>')
    return path


def collected_file(tmp_path, name, ids):
    path = tmp_path / name
    path.write_text("\n".join(ids) + f"\n\n{len(ids)} tests collected in 0.10s\n")
    return path


PASSING = [("tests.test_search", "test_a", "passed"), ("tests.test_search", "test_b", "passed"),
           ("tests.test_menu", "test_c", "passed")]


def test_check_passes_when_all_tests_ran(tmp_path):
    problems, lines = gate.check(gate.read_junit(junit_file(tmp_path, PASSING)), POLICY)

    assert problems == []
    assert "Ran 3 tests: 3 passed, 0 failed, 0 skipped (minimum 3)." in lines
    assert not any("can be raised" in line for line in lines)


def test_check_fails_when_a_test_was_deleted(tmp_path):
    problems, _ = gate.check(gate.read_junit(junit_file(tmp_path, PASSING[:2])), POLICY)

    assert len(problems) == 1
    assert "fewer than min_tests = 3" in problems[0]


def test_check_suggests_raising_min_tests(tmp_path):
    cases = PASSING + [("tests.test_menu", "test_d", "passed")]

    problems, lines = gate.check(gate.read_junit(junit_file(tmp_path, cases)), POLICY)

    assert problems == []
    assert "min_tests can be raised to 4 in backend/ci/test_policy.json." in lines


def test_check_fails_on_failed_and_error_tests(tmp_path):
    cases = PASSING + [("tests.test_menu", "test_d", "failed"), ("tests.test_menu", "test_e", "error")]

    problems, _ = gate.check(gate.read_junit(junit_file(tmp_path, cases)), POLICY)

    assert problems == ["2 test(s) failed: tests.test_menu::test_d, tests.test_menu::test_e"]


def test_check_allows_listed_skip(tmp_path):
    cases = PASSING + [("tests.test_seed", "test_live_seed", "skipped")]

    problems, lines = gate.check(gate.read_junit(junit_file(tmp_path, cases)), POLICY)

    assert problems == []
    assert "| `tests.test_seed::test_live_seed` | seed files missing | yes |" in lines


def test_check_fails_on_unlisted_skip_or_xfail(tmp_path):
    cases = PASSING + [("tests.test_menu", "test_new", "skipped"), ("tests.test_menu", "test_old", "xfail")]

    problems, lines = gate.check(gate.read_junit(junit_file(tmp_path, cases)), POLICY)

    assert [p.split(" (")[0] for p in problems] == [
        "Unexpected skip: tests.test_menu::test_new",
        "Unexpected skip: tests.test_menu::test_old",
    ]
    assert "## Problems" in lines


def test_skipped_tests_do_not_count_as_passed(tmp_path):
    cases = PASSING[:2] + [("tests.test_seed", "test_live_seed", "skipped")]

    problems, lines = gate.check(gate.read_junit(junit_file(tmp_path, cases)), POLICY)

    assert problems == []  # 3 tests ran, the skip is allowed
    assert "Ran 3 tests: 2 passed, 0 failed, 1 skipped (minimum 3)." in lines


def test_read_collected_keeps_only_node_ids(tmp_path):
    path = collected_file(tmp_path, "head.txt", ["tests/test_a.py::test_x", "tests/test_a.py::test_y[1-2]"])

    assert gate.read_collected(path) == {"tests/test_a.py::test_x", "tests/test_a.py::test_y[1-2]"}
    assert gate.read_collected(tmp_path / "missing.txt") is None
    assert gate.read_collected(None) is None
    assert gate.read_collected(collected_file(tmp_path, "empty.txt", [])) is None


def test_read_collected_ignores_random_uuid_parameters(tmp_path):
    base = collected_file(tmp_path, "base.txt", ["tests/test_a.py::test_x[fc465ebf-d626-49a6-9a3c-0411b8b92a40]"])
    head = collected_file(tmp_path, "head.txt", ["tests/test_a.py::test_x[202ec28d-0cf3-4756-8727-d79fe4566aee]"])

    assert gate.read_collected(base) == gate.read_collected(head) == {"tests/test_a.py::test_x[<uuid>]"}


def test_removed_tests_are_listed():
    base = {"tests/test_a.py::test_x", "tests/test_a.py::test_y", "tests/test_b.py::test_z"}
    head = {"tests/test_a.py::test_x", "tests/test_b.py::test_z_renamed", "tests/test_c.py::test_new"}

    lines = gate.removed_tests_lines(base, head)

    assert "3 tests in the base, 3 in this PR: 2 added, 2 removed." in lines
    assert lines[-3:] == ["| `tests/test_a.py::test_y` |", "| `tests/test_b.py::test_z` |", ""]


def test_no_removed_tests_prints_only_the_counts():
    ids = {"tests/test_a.py::test_x"}

    lines = gate.removed_tests_lines(ids, ids | {"tests/test_a.py::test_new"})

    assert lines[2:] == ["1 tests in the base, 2 in this PR: 1 added, 0 removed.", ""]


def test_long_removed_list_is_cut(monkeypatch):
    monkeypatch.setattr(gate, "MAX_LISTED_REMOVED", 2)
    base = {f"tests/test_a.py::test_{i}" for i in range(5)}

    lines = gate.removed_tests_lines(base, {"tests/test_b.py::test_x"})

    assert "| ... and 3 more |" in lines
    assert sum(line.startswith("| `") for line in lines) == 2


def test_missing_collection_is_reported_not_compared():
    lines = gate.removed_tests_lines(None, {"tests/test_a.py::test_x"})

    assert "Not compared: the test list of the base or of this PR could not be collected." in lines


def test_main_writes_summary_and_returns_exit_code(tmp_path, monkeypatch, capsys):
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(POLICY))
    monkeypatch.setattr(gate, "POLICY_PATH", policy_path)
    base = collected_file(tmp_path, "base.txt", ["tests/test_a.py::test_x", "tests/test_a.py::test_gone"])
    head = collected_file(tmp_path, "head.txt", ["tests/test_a.py::test_x"])
    summary = tmp_path / "summary.md"

    ok = gate.main([str(junit_file(tmp_path, PASSING)), "--base-tests", str(base), "--head-tests", str(head),
                    "--summary", str(summary)])
    failing = gate.main([str(junit_file(tmp_path, PASSING[:1]))])

    assert (ok, failing) == (0, 1)
    text = summary.read_text()
    assert "## Backend tests" in text
    assert "| `tests/test_a.py::test_gone` |" in text
    out = capsys.readouterr().out
    assert "::error::Only 1 tests ran" in out
    assert out.count("## Tests removed from the base") == 1  # only the run that passed both lists
