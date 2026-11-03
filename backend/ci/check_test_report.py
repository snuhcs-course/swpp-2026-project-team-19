"""Check the backend test run against backend/ci/test_policy.json and print a Markdown summary.

    python ci/check_test_report.py <junit.xml> [--base-tests FILE --head-tests FILE] [--summary FILE]

Fails (exit 1) when the run has failures or errors, when fewer tests ran than
min_tests (tests deleted or no longer collected), or when a test was skipped that
allowed_skips does not list (tests skipped or marked xfail instead of fixed).

With --base-tests and --head-tests (`pytest --collect-only -q` output of the PR's
base and of the PR), the tests that exist in the base but not in the PR are listed.
That list is reported only; it never fails the run, since renaming a test or
changing its parameters also removes its old ID.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

POLICY_PATH = Path(__file__).with_name("test_policy.json")
MAX_LISTED_REMOVED = 50
# Some tests are parametrized with uuid4(), so their IDs change on every collection.
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def read_junit(path: Path) -> dict:
    root = ET.parse(path).getroot()
    result = {"total": 0, "failed": [], "skipped": {}}
    for case in root.iter("testcase"):
        test_id = f"{case.get('classname')}::{case.get('name')}"
        result["total"] += 1
        if case.find("failure") is not None or case.find("error") is not None:
            result["failed"].append(test_id)
        skipped = case.find("skipped")
        if skipped is not None:
            result["skipped"][test_id] = skipped.get("message", "")
    return result


def read_collected(path: Path | None) -> set[str] | None:
    """Node IDs from `pytest --collect-only -q` with UUIDs replaced by <uuid>, or None when the
    file is missing or empty."""
    if path is None or not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    ids = {UUID.sub("<uuid>", line.strip()) for line in lines if "::" in line}
    return ids or None


def check(junit: dict, policy: dict) -> tuple[list[str], list[str]]:
    """Return (problems, Markdown summary lines)."""
    problems = []
    total, min_tests = junit["total"], policy["min_tests"]
    passed = total - len(junit["failed"]) - len(junit["skipped"])
    lines = ["## Backend tests", "",
             f"Ran {total} tests: {passed} passed, {len(junit['failed'])} failed, "
             f"{len(junit['skipped'])} skipped (minimum {min_tests}).", ""]
    if total > min_tests:
        lines += [f"min_tests can be raised to {total} in backend/ci/test_policy.json.", ""]

    if junit["failed"]:
        problems.append(f"{len(junit['failed'])} test(s) failed: " + ", ".join(junit["failed"]))
    if total < min_tests:
        problems.append(f"Only {total} tests ran, fewer than min_tests = {min_tests}. "
                        "A test was deleted or not collected; if that is intended, lower min_tests "
                        "in backend/ci/test_policy.json and say why in the PR.")

    allowed = policy["allowed_skips"]
    if junit["skipped"]:
        lines += ["| Skipped test | Reason | Allowed |", "|---|---|---|"]
        for test_id, message in sorted(junit["skipped"].items()):
            ok = test_id in allowed
            lines.append(f"| `{test_id}` | {message or allowed.get(test_id, '')} | {'yes' if ok else '**no**'} |")
            if not ok:
                problems.append(f"Unexpected skip: {test_id} ({message}). Fix the test, or add it to "
                                "allowed_skips in backend/ci/test_policy.json with a reason.")
        lines.append("")

    if problems:
        lines += ["## Problems", ""] + [f"- {p}" for p in problems] + [""]
    return problems, lines


def removed_tests_lines(base: set[str] | None, head: set[str] | None) -> list[str]:
    """Markdown lines listing the tests of the base that the PR no longer has (reported only)."""
    lines = ["## Tests removed from the base (reported, not enforced)", ""]
    if base is None or head is None:
        return lines + ["Not compared: the test list of the base or of this PR could not be collected.", ""]
    removed = sorted(base - head)
    lines.append(f"{len(base)} tests in the base, {len(head)} in this PR: "
                 f"{len(head - base)} added, {len(removed)} removed.")
    lines.append("")
    if removed:
        lines += ["Check that the PR says why each one was removed or renamed.", "", "| Removed test |", "|---|"]
        lines += [f"| `{test_id}` |" for test_id in removed[:MAX_LISTED_REMOVED]]
        if len(removed) > MAX_LISTED_REMOVED:
            lines.append(f"| ... and {len(removed) - MAX_LISTED_REMOVED} more |")
        lines.append("")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("junit", type=Path)
    parser.add_argument("--base-tests", type=Path, help="`pytest --collect-only -q` output of the PR's base")
    parser.add_argument("--head-tests", type=Path, help="`pytest --collect-only -q` output of the PR")
    parser.add_argument("--summary", type=Path, help="append the Markdown summary to this file")
    args = parser.parse_args(argv)

    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    problems, lines = check(read_junit(args.junit), policy)
    if args.base_tests or args.head_tests:
        lines += removed_tests_lines(read_collected(args.base_tests), read_collected(args.head_tests))

    text = "\n".join(lines) + "\n"
    print(text)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as f:
            f.write(text)
    for problem in problems:
        print(f"::error::{problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
