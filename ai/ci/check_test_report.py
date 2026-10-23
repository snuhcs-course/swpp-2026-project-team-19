"""Check the AI test run against ai/ci/test_policy.json and print a Markdown summary.

    python ai/ci/check_test_report.py <junit.xml> <coverage.json> [--summary FILE]

Fails (exit 1) when the run has failures or errors, when fewer tests ran than
min_tests (tests deleted), or when a test was skipped that allowed_skips does not
list (tests skipped or marked xfail instead of fixed). Coverage per component is
compared with coverage_targets and reported only; it never fails the run.
"""

from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

POLICY_PATH = Path(__file__).with_name("test_policy.json")


def read_junit(path: Path) -> dict:
    root = ET.parse(path).getroot()
    cases = root.iter("testcase")
    result = {"total": 0, "failed": [], "skipped": {}}
    for case in cases:
        test_id = f"{case.get('classname')}::{case.get('name')}"
        result["total"] += 1
        if case.find("failure") is not None or case.find("error") is not None:
            result["failed"].append(test_id)
        skipped = case.find("skipped")
        if skipped is not None:
            result["skipped"][test_id] = skipped.get("message", "")
    return result


def component_coverage(coverage_json: dict, components: list[str]) -> dict[str, float]:
    """Line + branch coverage per component directory, as coverage.py computes it."""
    totals = {c: [0, 0] for c in components}  # covered, total
    for path, data in coverage_json["files"].items():
        path = path.replace("\\", "/")
        for component in components:
            if path.startswith(component + "/"):
                s = data["summary"]
                totals[component][0] += s["covered_lines"] + s.get("covered_branches", 0)
                totals[component][1] += s["num_statements"] + s.get("num_branches", 0)
    return {c: (100.0 * covered / total if total else 0.0) for c, (covered, total) in totals.items()}


def check(junit: dict, coverage: dict[str, float], policy: dict) -> tuple[list[str], list[str]]:
    """Return (problems, Markdown summary lines)."""
    problems = []
    passed = junit["total"] - len(junit["failed"]) - len(junit["skipped"])
    lines = ["## AI tests", "",
             f"Ran {junit['total']} tests: {passed} passed, {len(junit['failed'])} failed, "
             f"{len(junit['skipped'])} skipped (minimum {policy['min_tests']}).", ""]

    if junit["failed"]:
        problems.append(f"{len(junit['failed'])} test(s) failed: " + ", ".join(junit["failed"]))
    if junit["total"] < policy["min_tests"]:
        problems.append(f"Only {junit['total']} tests ran, fewer than min_tests = {policy['min_tests']}. "
                        "A test was deleted or not collected; if that is intended, lower min_tests "
                        "in ai/ci/test_policy.json and say why in the PR.")

    allowed = policy["allowed_skips"]
    if junit["skipped"]:
        lines += ["| Skipped test | Reason | Allowed |", "|---|---|---|"]
        for test_id, message in sorted(junit["skipped"].items()):
            ok = test_id in allowed
            lines.append(f"| `{test_id}` | {message or allowed.get(test_id, '')} | {'yes' if ok else '**no**'} |")
            if not ok:
                problems.append(f"Unexpected skip: {test_id} ({message}). Fix the test, or add it to "
                                "allowed_skips in ai/ci/test_policy.json with a reason.")
        lines.append("")

    lines += ["## AI coverage (reported, not enforced)", "",
              "| Component | Target | Actual | |", "|---|---|---|---|"]
    for component, target in policy["coverage_targets"].items():
        actual = coverage.get(component, 0.0)
        mark = "meets target" if actual >= target else "below target"
        lines.append(f"| `{component}` | {target}% | {actual:.1f}% | {mark} |")
    lines.append("")

    if problems:
        lines += ["## Problems", ""] + [f"- {p}" for p in problems] + [""]
    return problems, lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("junit", type=Path)
    parser.add_argument("coverage", type=Path)
    parser.add_argument("--summary", type=Path, help="append the Markdown summary to this file")
    args = parser.parse_args(argv)

    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    junit = read_junit(args.junit)
    coverage = component_coverage(json.loads(args.coverage.read_text(encoding="utf-8")),
                                  list(policy["coverage_targets"]))
    problems, lines = check(junit, coverage, policy)

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
