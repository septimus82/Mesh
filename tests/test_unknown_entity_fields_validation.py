import json
import tempfile
import unittest
from pathlib import Path

import pytest

from engine.scene_loader import SceneLoader

pytestmark = pytest.mark.builtin_behaviours

class TestUnknownEntityFieldsValidation(unittest.TestCase):
    def setUp(self):
        self.loader = SceneLoader()
        self.test_dir = tempfile.mkdtemp()
        self.scene_path = Path(self.test_dir) / "test_scene.json"

        self.scene_data = {
            "name": "Test Scene",
            "entities": [
                {
                    "name": "ValidEntity",
                    "x": 0,
                    "y": 0,
                    "sprite": "test.png"
                },
                {
                    "name": "InvalidEntity",
                    "x": 10,
                    "y": 10,
                    "sprite": "test.png",
                    "encoutner_group": "typo" # Unknown field
                }
            ]
        }
        self.scene_path.write_text(json.dumps(self.scene_data), encoding="utf-8")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.test_dir)

    def test_non_strict_validation(self):
        # Should warn but pass
        report = self.loader.validate_scene_file(str(self.scene_path), strict=False)
        self.assertTrue(report.ok, "Non-strict validation should pass")

        # Check for warning
        warnings = [w for w in report.warnings if "unknown field 'encoutner_group'" in w]
        self.assertTrue(len(warnings) > 0, f"Expected warning about unknown field, got: {report.warnings}")

    def test_strict_validation(self):
        # Should fail
        report = self.loader.validate_scene_file(str(self.scene_path), strict=True)
        self.assertFalse(report.ok, "Strict validation should fail")

        # Check for error
        errors = [e for e in report.errors if "unknown field 'encoutner_group'" in e]
        self.assertTrue(len(errors) > 0, f"Expected error about unknown field, got: {report.errors}")

if __name__ == "__main__":
    unittest.main()
