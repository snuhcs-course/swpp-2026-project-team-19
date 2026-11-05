"""Regression tests for the standalone JaCoCo HTML parser.

AI-assisted with ChatGPT (2026-11-05). Human review required.
"""

import unittest

from report_coverage import class_group, coverage_totals, percent, table_rows


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


if __name__ == "__main__":
    unittest.main()
