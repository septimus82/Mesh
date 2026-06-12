import unittest
from pathlib import Path
from unittest.mock import patch

from engine.tooling.validate_all import UnifiedValidator


class TestThemeReferenceValidation(unittest.TestCase):
    def setUp(self):
        self.validator = UnifiedValidator(Path("."))
        self.validator.warnings = []
        self.validator.errors = []

    def test_validate_valid_theme(self):
        themes_json = '{"moss": {"encounter_set_id": "moss_encounters"}}'
        sets_json = '{"encounter_sets": [{"id": "moss_encounters"}]}'

        with patch("pathlib.Path.read_text", side_effect=[themes_json, sets_json]):
            with patch("pathlib.Path.exists", return_value=True):
                data = {"settings": {"region_theme": "moss"}}
                result = self.validator.validate_region_theme(Path("scene.json"), data)

                self.assertTrue(result)
                self.assertEqual(len(self.validator.errors), 0)

    def test_validate_invalid_theme(self):
        themes_json = '{}'
        sets_json = '{"encounter_sets": []}'

        with patch("pathlib.Path.read_text", side_effect=[themes_json, sets_json]):
            with patch("pathlib.Path.exists", return_value=True):
                data = {"settings": {"region_theme": "missing"}}
                result = self.validator.validate_region_theme(Path("scene.json"), data)

                self.assertFalse(result)
                self.assertIn("Unknown region_theme 'missing'", self.validator.errors[0])

    def test_validate_invalid_encounter_set_ref(self):
        themes_json = '{"moss": {"encounter_set_id": "missing_set"}}'
        sets_json = '{"encounter_sets": []}'

        with patch("pathlib.Path.read_text", side_effect=[themes_json, sets_json]):
            with patch("pathlib.Path.exists", return_value=True):
                data = {"settings": {"region_theme": "moss"}}
                result = self.validator.validate_region_theme(Path("scene.json"), data)

                self.assertFalse(result)
                self.assertIn("references unknown encounter_set 'missing_set'", self.validator.errors[0])

    def test_validate_invalid_encounter_set_override(self):
        themes_json = '{}'
        sets_json = '{"encounter_sets": []}'

        with patch("pathlib.Path.read_text", side_effect=[themes_json, sets_json]):
            with patch("pathlib.Path.exists", return_value=True):
                data = {"settings": {"encounter_set_id": "missing_set"}}
                result = self.validator.validate_region_theme(Path("scene.json"), data)

                self.assertFalse(result)
                self.assertIn("Unknown encounter_set_id 'missing_set'", self.validator.errors[0])
