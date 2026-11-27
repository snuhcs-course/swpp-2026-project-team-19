"""Exercise the production Gradle version script in isolated Git/Gradle fixtures."""

import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
VERSION_SCRIPT = ROOT / "android" / "versioning.gradle.kts"
WRAPPER = ROOT / ("gradlew.bat" if os.name == "nt" else "gradlew")


class BuildVersioningTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="bottlemap-version-")
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        (self.project / "settings.gradle.kts").write_text(
            'rootProject.name = "version-fixture"\n', encoding="utf-8"
        )
        (self.project / "build.gradle.kts").write_text(
            'plugins { base }\n'
            f'apply(from = "{VERSION_SCRIPT.as_posix()}")\n', encoding="utf-8"
        )
        self.git("init", "--quiet")
        self.git("add", "settings.gradle.kts", "build.gradle.kts")
        self.git("-c", "user.name=Version Test", "-c", "user.email=test@example.invalid",
                 "commit", "--quiet", "-m", "Version fixture")
        self.counter = self.project / ".gradle" / "bottlemap" / "version-code"

    def git(self, *args):
        return subprocess.run(
            ["git", *args], cwd=self.project, check=True,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )

    def gradle(self, *args, success=True):
        result = subprocess.run(
            [str(WRAPPER), "--project-dir", str(self.project), "--console=plain",
             *args], cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180,
        )
        output = result.stdout + result.stderr
        if success:
            self.assertEqual(result.returncode, 0, output)
        else:
            self.assertNotEqual(result.returncode, 0, output)
        return output

    def code(self, output):
        match = re.search(r"BottleMap version: ([^ ]+) \((\d+)\)", output)
        self.assertIsNotNone(match, output)
        return int(match.group(2))

    def write_counter(self, value):
        self.counter.parent.mkdir(parents=True, exist_ok=True)
        self.counter.write_text(str(value), encoding="utf-8")

    def test_rebuild_configuration_cache_and_clean_increase_code(self):
        first = self.code(self.gradle("help", "--configuration-cache"))
        second = self.code(self.gradle("help", "--configuration-cache"))
        third = self.code(self.gradle("clean", "--configuration-cache"))
        self.assertGreater(first, 1)
        self.assertGreater(second, first)
        self.assertGreater(third, second)
        self.assertEqual(int(self.counter.read_text()), third)

    def test_counter_protects_against_clock_rollback(self):
        self.write_counter(2_000_000_000)
        self.assertEqual(self.code(self.gradle("help")), 2_000_000_001)

    def test_corrupt_and_exhausted_counters_fail_without_overwriting(self):
        for value in ("broken", "-1", "2100000000"):
            with self.subTest(value=value):
                self.write_counter(value)
                self.gradle("help", success=False)
                self.assertEqual(self.counter.read_text(), value)

    def test_release_tag_must_match_version_name(self):
        self.git("tag", "android/v1.2.3")
        rejected = self.gradle("help", success=False)
        self.assertIn("do not match versionName", rejected)
        accepted = self.gradle("help", "-PBOTTLEMAP_VERSION_NAME=1.2.3")
        self.assertIn("BottleMap version: 1.2.3", accepted)
        self.assertIn("release tag: android/v1.2.3", accepted)

    def test_invalid_version_name_is_rejected(self):
        output = self.gradle("help", "-PBOTTLEMAP_VERSION_NAME=1.2", success=False)
        self.assertIn("must be major.minor.patch", output)


if __name__ == "__main__":
    unittest.main()
