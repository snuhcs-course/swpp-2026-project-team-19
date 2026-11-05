"""Regression tests for Android JUnit XML inventory/skip policy (JVM and Emulator)."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from check_test_report import validate


class TestInventoryPolicyTest(unittest.TestCase):
    def make_report(self, directory: Path, *, instrumented=False, skipped=False, failed=False):
        path = directory / "TEST-fixture.xml"
        testcase = '<testcase classname="bottlemap.Fixture" name="works">'
        if skipped:
            testcase += "<skipped/>"
        if failed:
            testcase += "<failure/>"
        testcase += "</testcase>"
        suite = (
            f'<testsuite name="bottlemap.Fixture" tests="1" failures="{int(failed)}" '
            f'errors="0" skipped="{int(skipped)}">{testcase}</testsuite>'
        )
        content = f'<testsuites tests="1" skipped="{int(skipped)}">{suite}</testsuites>' if instrumented else suite
        path.write_text(content, encoding="utf-8")
        return path

    def test_jvm_report_with_baseline_passes(self):
        with TemporaryDirectory() as d:
            p = self.make_report(Path(d))
            result = validate("jvm", {"jvm": {"min_tests": 1, "allowed_skips": {}}}, [p])
            self.assertEqual((result["tests"], result["executed"]), (1, 1))

    def test_instrumentation_testsuites_format_passes(self):
        with TemporaryDirectory() as d:
            p = self.make_report(Path(d), instrumented=True)
            result = validate(
                "instrumentation", {"instrumentation": {"min_tests": 1, "allowed_skips": {}}}, [p]
            )
            self.assertEqual(result["executed"], 1)

    def test_missing_reports_fail(self):
        with self.assertRaisesRegex(ValueError, "No jvm"):
            validate("jvm", {"jvm": {"min_tests": 1, "allowed_skips": {}}}, [])

    def test_dropped_tests_fail(self):
        with TemporaryDirectory() as d:
            p = self.make_report(Path(d))
            with self.assertRaisesRegex(ValueError, "expected at least 2"):
                validate("jvm", {"jvm": {"min_tests": 2, "allowed_skips": {}}}, [p])

    def test_unknown_skips_fail(self):
        with TemporaryDirectory() as d:
            p = self.make_report(Path(d), skipped=True)
            with self.assertRaisesRegex(ValueError, "Unapproved skipped"):
                validate("jvm", {"jvm": {"min_tests": 1, "allowed_skips": {}}}, [p])

    def test_allowed_skip_still_counts_toward_executed_minimum(self):
        with TemporaryDirectory() as d:
            p = self.make_report(Path(d), skipped=True)
            with self.assertRaisesRegex(ValueError, "executed 0"):
                validate("jvm", {"jvm": {"min_tests": 1, "allowed_skips": {
                    "bottlemap.Fixture#works": "temporary exception"
                }}}, [p])

    def test_failure_is_not_suppressed(self):
        with TemporaryDirectory() as d:
            p = self.make_report(Path(d), failed=True)
            with self.assertRaisesRegex(ValueError, "tests failed"):
                validate("jvm", {"jvm": {"min_tests": 1, "allowed_skips": {}}}, [p])

    def test_bad_xml_counts_fail(self):
        with TemporaryDirectory() as d:
            p = self.make_report(Path(d))
            p.write_text(p.read_text().replace('tests="1"', 'tests="2"'))
            with self.assertRaisesRegex(ValueError, "count mismatch"):
                validate("jvm", {"jvm": {"min_tests": 1, "allowed_skips": {}}}, [p])


if __name__ == "__main__":
    unittest.main()
