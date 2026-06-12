import json
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.tooling.validate_all import UnifiedValidator


class TestThemeValidation(unittest.TestCase):
    def setUp(self):
        self.validator = UnifiedValidator(Path("."))
        self.mock_themes = {
            "moss": {}
        }

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    def test_validate_valid_theme(self, mock_read, mock_exists):
        mock_exists.return_value = True
        mock_read.return_value = json.dumps(self.mock_themes)

        data = {
            "settings": {
                "region_theme": "moss"
            }
        }

        result = self.validator.validate_region_theme(Path("scene.json"), data)
        self.assertTrue(result)
        self.assertEqual(len(self.validator.errors), 0)

    @patch("pathlib.Path.exists")
    @patch("pathlib.Path.read_text")
    def test_validate_invalid_theme(self, mock_read, mock_exists):
        mock_exists.return_value = True
        mock_read.return_value = json.dumps(self.mock_themes)

        data = {
            "settings": {
                "region_theme": "invalid_theme"
            }
        }

        result = self.validator.validate_region_theme(Path("scene.json"), data)
        self.assertFalse(result)
        self.assertIn("Unknown region_theme 'invalid_theme'", self.validator.errors[0])

    @patch("pathlib.Path.exists")
    def test_validate_missing_registry(self, mock_exists):
        mock_exists.return_value = False # themes.json missing

        data = {
            "settings": {
                "region_theme": "moss"
            }
        }

        result = self.validator.validate_region_theme(Path("scene.json"), data)
        self.assertTrue(result) # Should warn, not fail validation logic itself (or depends on implementation)
        self.assertEqual(len(self.validator.warnings), 1)

if __name__ == "__main__":
    unittest.main()
