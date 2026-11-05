"""Regression tests for the standalone JaCoCo HTML parser.

AI-assisted with ChatGPT (2026-11-05). Human review required.
"""

import unittest
import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from report_coverage import class_group, coverage_totals, percent, summarize, table_rows


class CoverageReportParserTest(unittest.TestCase):
    def test_total_counters_are_line_based_not_instruction_based(self):
        cells = [
            "Total", "197,441 of 221,058", "10%", "11,105 of 13,538", "17%",
            "8,691", "10,395", "15,886", "18,690", "3,290", "4,157", "436", "609",
        ]
        self.assertEqual(coverage_totals(cells)["covered_lines"], 2804)
        self.assertEqual(coverage_totals(cells)["covered_branches"], 2433)
        self.assertEqual(percent(2804, 18690), "15.00%")

    def test_bad_or_incomplete_counters_are_rejected(self):
        cells = [
            "Total", "5 of 10", "50%", "1 of 2", "50%",
            "1", "1", "11", "10", "1", "1", "1", "1",
        ]
        with self.assertRaisesRegex(ValueError, "Invalid JaCoCo counter"):
            coverage_totals(cells)
        with self.assertRaisesRegex(ValueError, "Expected 13"):
            coverage_totals(cells[:-1])

    def test_extracts_rows_and_classification_without_extra_libraries(self):
        document = "<table><tbody><tr><td><a href='x'>AuthViewModel</a></td><td>2</td></tr></tbody></table>"
        self.assertEqual(table_rows(document, "tbody"), [["AuthViewModel", "2"]])
        self.assertEqual(class_group("OwnerViewModel"), "ViewModel-related")
        self.assertEqual(class_group("BarDto"), "Mapper/DTO-related")
        self.assertEqual(class_group("BackendSearchRepository"), "Repository/Source-related")
        self.assertIsNone(class_group("CustomerScreenKt"))


    @staticmethod
    def _write_report_index(report_dir: Path, missed_lines: int = 2) -> None:
        # JaCoCo's footer uses 13 cells; overall line coverage is nonzero.
        cells = [
            "Total", "2 of 10", "80%", "1 of 4", "75%",
            "2", "4", str(missed_lines), "8", "1", "1", "1", "1",
        ]
        report_dir.joinpath("index.html").write_text(
            "<table><tfoot><tr>" + "".join(f"<td>{c}</td>" for c in cells)
            + "</tr></tfoot></table>", encoding="utf-8"
        )

    def test_exploratory_groups_can_all_be_empty(self):
        # No matching package/class names must not fail a valid overall report.
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_report_index(root)
            result = summarize(root)
            self.assertEqual(result["overall"]["covered_lines"], 6)
            self.assertEqual(len(result["groups"]), 3)
            for metrics in result["groups"].values():
                self.assertEqual(metrics["classes"], 0)
                self.assertEqual(metrics["total_lines"], 0)
                self.assertEqual(percent(metrics["covered_lines"], metrics["total_lines"]), "N/A")

    def test_only_some_exploratory_groups_present(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_report_index(root)
            package = root / "com.zerotoone.bottlemap.ui.customer"
            package.mkdir()
            cells = [
                "SearchViewModel", "2 of 10", "80%", "1 of 4", "75%",
                "2", "4", "2", "8", "1", "1", "1", "1",
            ]
            package.joinpath("index.html").write_text(
                "<table><tbody><tr>" + "".join(f"<td>{c}</td>" for c in cells)
                + "</tr></tbody></table>", encoding="utf-8"
            )
            result = summarize(root)
            self.assertEqual(result["groups"]["ViewModel-related"]["covered_lines"], 6)
            self.assertEqual(result["groups"]["ViewModel-related"]["classes"], 1)
            self.assertEqual(result["groups"]["Mapper/DTO-related"]["total_lines"], 0)
            self.assertEqual(result["groups"]["Repository/Source-related"]["total_lines"], 0)

    def test_zero_covered_lines_still_fail_ci(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_report_index(root, missed_lines=8)
            with self.assertRaisesRegex(ValueError, "zero executable or covered"):
                summarize(root)


    def test_instrumentation_cli_labels_and_records_coverage_provenance(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_report_index(root)
            command = [
                sys.executable, str(Path(__file__).with_name("report_coverage.py")),
                "--kind", "instrumentation", directory,
            ]
            env = {k: v for k, v in os.environ.items() if k != "GITHUB_STEP_SUMMARY"}
            result = subprocess.run(command, check=True, capture_output=True, text=True, env=env)
            self.assertIn("Android instrumentation / Compose coverage", result.stdout)
            self.assertNotIn("## Android JVM unit-test coverage", result.stdout)
            self.assertIn("API 35 emulator", result.stdout)
            self.assertEqual(
                json.loads((root / "coverage-summary.json").read_text())["coverage_kind"],
                "instrumentation"
            )

    def test_jvm_cli_retains_distinct_unit_test_label(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_report_index(root)
            env = {k: v for k, v in os.environ.items() if k != "GITHUB_STEP_SUMMARY"}
            result = subprocess.run([
                sys.executable, str(Path(__file__).with_name("report_coverage.py")), directory,
            ], check=True, capture_output=True, text=True, env=env)
            self.assertIn("Android JVM unit-test coverage", result.stdout)
            self.assertNotIn("## Android instrumentation / Compose coverage", result.stdout)
            self.assertEqual(
                json.loads((root / "coverage-summary.json").read_text())["coverage_kind"], "jvm"
            )


if __name__ == "__main__":
    unittest.main()
