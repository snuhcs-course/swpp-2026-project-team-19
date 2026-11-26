import json
from pathlib import Path
import tempfile
import unittest
from prepare_firebase import prepare


class PrepareFirebaseTest(unittest.TestCase):
    def test_missing_secret_does_not_create_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "google-services.json"
            self.assertFalse(prepare("", target))
            self.assertFalse(target.exists())

    def test_valid_configuration_is_written_without_transformation(self):
        raw = json.dumps({"client": [{"client_info": {"android_client_info": {
            "package_name": "com.zerotoone.bottlemap"}}}]})
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "google-services.json"
            self.assertTrue(prepare(raw, target))
            self.assertEqual(raw, target.read_text(encoding="utf-8"))

    def test_invalid_json_or_wrong_app_leaves_no_file_and_never_echoes_input(self):
        for raw in ("PRIVATE_VALUE", "[]", '{"client":[null]}', '{"client":[{"client_info":null}]}',
                    '{"client":[{"client_info":{"android_client_info":{"package_name":"wrong"}}}]}'):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "google-services.json"
                with self.assertRaisesRegex(ValueError, "^Invalid Firebase Android configuration$"):
                    prepare(raw, target)
                self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
