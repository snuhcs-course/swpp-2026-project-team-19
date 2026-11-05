#!/usr/bin/env python3
"""Enforce observed Android test inventories and explicit skip policy in CI.

Reads Gradle JUnit XML (JVM) or Android connected-test XML (instrumentation).
AI-assisted (2026-11-05); the team should review baseline changes.
"""
import argparse
import glob
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET


REPORT_GLOBS = {
    "jvm": "android/app/build/test-results/testDebugUnitTest/TEST-*.xml",
    "instrumentation": "android/app/build/outputs/androidTest-results/connected/debug/TEST-*.xml",
}


def validate(kind: str, policy: dict, paths: list[Path]) -> dict:
    if kind not in REPORT_GLOBS:
        raise ValueError(f"Unsupported test kind: {kind}")
    if not paths:
        raise ValueError(f"No {kind} JUnit XML reports found")
    config = policy[kind]
    minimum = int(config["min_tests"])
    if minimum <= 0:
        raise ValueError("Minimum test count must be positive")
    allowed = config.get("allowed_skips", {})
    if not isinstance(allowed, dict):
        raise ValueError("allowed_skips must be a mapping of test IDs to reasons")
    tests = failures = errors = 0
    skipped_ids = []
    test_ids = set()
    for path in paths:
        root = ET.parse(path).getroot()
        if root.tag not in ("testsuite", "testsuites"):
            raise ValueError(f"Unsupported JUnit root in {path}: {root.tag}")
        cases = list(root.iter("testcase"))
        if "tests" in root.attrib and int(root.attrib["tests"]) != len(cases):
            raise ValueError(f"JUnit test count mismatch in {path}")
        tests += len(cases)
        for case in cases:
            ident = f'{case.get("classname", "")}#{case.get("name", "")}'
            if ident in test_ids:
                raise ValueError(f"Duplicate test ID in reports: {ident}")
            test_ids.add(ident)
            if case.find("failure") is not None:
                failures += 1
            if case.find("error") is not None:
                errors += 1
            if case.find("skipped") is not None:
                skipped_ids.append(ident)
        if "skipped" in root.attrib and int(root.attrib["skipped"]) != sum(
            1 for case in cases if case.find("skipped") is not None
        ):
            raise ValueError(f"JUnit skipped count mismatch in {path}")
    skipped = len(skipped_ids)
    executed = tests - skipped
    unapproved = sorted(set(skipped_ids) - set(allowed))
    if unapproved:
        raise ValueError(f"Unapproved skipped {kind} tests: {', '.join(unapproved)}")
    if failures or errors:
        raise ValueError(f"{kind} tests failed: failures={failures}, errors={errors}")
    if executed < minimum:
        raise ValueError(
            f"{kind} executed {executed} tests; expected at least {minimum} "
            f"(total={tests}, skipped={skipped})"
        )
    return {
        "kind": kind, "tests": tests, "executed": executed,
        "failures": failures, "errors": errors, "skipped": skipped,
        "minimum": minimum, "reports": len(paths),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=REPORT_GLOBS)
    parser.add_argument("--policy", type=Path, default=Path("android/ci/test_policy.json"))
    args = parser.parse_args()
    policy = json.loads(args.policy.read_text(encoding="utf-8"))
    results = validate(args.kind, policy, [Path(p) for p in sorted(glob.glob(REPORT_GLOBS[args.kind]))])
    msg = (
        f"| {results['kind']} | {results['tests']} | {results['executed']} | "
        f"{results['skipped']} | {results['minimum']} | Passed |"
    )
    print(msg)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write("\n## Android test inventory policy\n\n")
            f.write("| Suite | Total | Executed | Skipped | Minimum | Result |\n")
            f.write("|---|---:|---:|---:|---:|---|\n")
            f.write(msg + "\n")
    print(f"Validated {results['reports']} JUnit XML file(s) with no unapproved skips")


if __name__ == "__main__":
    main()
