#!/usr/bin/env python3
"""Validate and summarize AGP's JaCoCo HTML report for JVM local unit tests.

AI-assisted with ChatGPT (2026-11-05). Human review required before merge.
"""

import argparse
import html
import json
import os
from pathlib import Path
import re


ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.DOTALL)
CELL_RE = re.compile(r"<td\b[^>]*>(.*?)</td>", re.DOTALL)
TAG_RE = re.compile(r"<[^>]*>")


def table_rows(document: str, section: str) -> list[list[str]]:
    match = re.search(rf"<{section}>(.*?)</{section}>", document, re.DOTALL)
    if not match:
        raise ValueError(f"Missing JaCoCo {section} table section")
    return [
        [html.unescape(TAG_RE.sub("", cell)).strip() for cell in CELL_RE.findall(row)]
        for row in ROW_RE.findall(match.group(1))
    ]


def count(value: str) -> int:
    return int(value.replace(",", ""))


def coverage_totals(cells: list[str]) -> dict[str, int]:
    if len(cells) != 13:
        raise ValueError(f"Expected 13 JaCoCo total columns, got {len(cells)}")
    missed_instructions, total_instructions = map(count, re.findall(r"[\d,]+", cells[1]))
    missed_branches, total_branches = map(count, re.findall(r"[\d,]+", cells[3]))
    missed_lines, total_lines = count(cells[7]), count(cells[8])
    for missed, total in (
        (missed_instructions, total_instructions),
        (missed_branches, total_branches),
        (missed_lines, total_lines),
    ):
        if not 0 <= missed <= total:
            raise ValueError(f"Invalid JaCoCo counter: missed={missed}, total={total}")
    return {
        "covered_instructions": total_instructions - missed_instructions,
        "total_instructions": total_instructions,
        "covered_branches": total_branches - missed_branches,
        "total_branches": total_branches,
        "covered_lines": total_lines - missed_lines,
        "total_lines": total_lines,
    }


def percent(covered: int, total: int) -> str:
    return f"{100 * covered / total:.2f}%" if total else "N/A"


def class_group(class_name: str) -> str | None:
    # Exploratory classification only, NOT a team-approved coverage denominator.
    if "ViewModel" in class_name:
        return "ViewModel-related"
    if "Mapper" in class_name or "Dto" in class_name or "DTO" in class_name:
        return "Mapper/DTO-related"
    if "Repository" in class_name or "Source" in class_name:
        return "Repository/Source-related"
    return None


def summarize(report_dir: Path) -> dict:
    landing = report_dir / "index.html"
    if not landing.is_file() or not landing.stat().st_size:
        raise ValueError(f"Missing or empty JaCoCo HTML index: {landing}")
    totals = table_rows(landing.read_text(encoding="utf-8"), "tfoot")
    if len(totals) != 1 or totals[0][0] != "Total":
        raise ValueError("JaCoCo report lacks the Total row")
    overall = coverage_totals(totals[0])
    if overall["total_lines"] == 0 or overall["covered_lines"] == 0:
        raise ValueError("JaCoCo measured zero executable or covered app lines")

    groups = {
        group: {"covered_lines": 0, "total_lines": 0, "classes": 0}
        for group in ("ViewModel-related", "Mapper/DTO-related", "Repository/Source-related")
    }
    for package_index in report_dir.glob("com.zerotoone.bottlemap*/index.html"):
        for cells in table_rows(package_index.read_text(encoding="utf-8"), "tbody"):
            if not cells:
                continue
            group = class_group(cells[0])
            if group is None:
                continue
            # JaCoCo omits empty instruction/branch bar cells on some class rows.
            # The final six metric columns (Missed Lines, Lines, ...) are stable.
            missed, total = count(cells[-6]), count(cells[-5])
            if not 0 <= missed <= total:
                raise ValueError(f"Invalid JaCoCo class line counter in {package_index}")
            groups[group]["covered_lines"] += total - missed
            groups[group]["total_lines"] += total
            groups[group]["classes"] += 1

    # Class-name buckets are exploratory, not a CI quality gate. A rename or
    # refactor may leave a bucket empty even when overall coverage is valid.
    # The summary displays N/A for zero denominators via percent().
    return {"overall": overall, "groups": groups}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_dir", type=Path)
    args = parser.parse_args()
    results = summarize(args.report_dir)
    overall = results["overall"]

    report = [
        "## Android JVM unit-test coverage (JaCoCo)",
        "",
        "| Metric | Covered | Total | Coverage |",
        "|---|---:|---:|---:|",
    ]
    for metric in ("lines", "branches", "instructions"):
        covered, total = overall[f"covered_{metric}"], overall[f"total_{metric}"]
        report.append(f"| {metric.title()} | {covered:,} | {total:,} | {percent(covered, total)} |")
    report += [
        "",
        "Exploratory class-name grouping (not an approved threshold):",
        "",
        "| Layer | Covered lines | Total lines | Line coverage |",
        "|---|---:|---:|---:|",
    ]
    for layer, metrics in results["groups"].items():
        report.append(
            f"| {layer} | {metrics['covered_lines']:,} | {metrics['total_lines']:,} | "
            f"{percent(metrics['covered_lines'], metrics['total_lines'])} |"
        )
    report += [
        "",
        "JVM coverage includes compiled Compose/UI classes in the overall denominator; "
        "it does not establish on-device or SDK behavior. "
        "This CI check validates report integrity and nonzero coverage only; "
        "no team-approved numerical percentage gate is applied.",
        "",
    ]
    summary = "\n".join(report)
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
            stream.write(summary + "\n")
    (args.report_dir / "coverage-summary.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
