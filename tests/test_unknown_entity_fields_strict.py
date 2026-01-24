import pytest
import unittest
import json
import tempfile
from pathlib import Path
from engine.scene_loader import SceneLoader


pytestmark = pytest.mark.builtin_behaviours

class TestUnknownEntityFieldsStrict(unittest.TestCase):
    def test_unknown_fields_strict(self):
        """Ensure unknown fields cause errors in strict mode, warnings otherwise."""
        loader = SceneLoader()
        
        # Scene with unknown field in entity
        scene_data = {
            "name": "Test Scene",
            "entities": [
                {
                    "name": "Player",
                    "x": 0,
                    "y": 0,
                    "unknown_field": "should_warn_or_error"
                }
            ]
        }
        
        # Non-strict: Should warn
        report = loader.validate_scene(scene_data, strict=False)
        self.assertTrue(report.ok, "Non-strict validation should pass")
        self.assertTrue(any("unknown field 'unknown_field'" in w for w in report.warnings), 
                        "Should warn about unknown field in non-strict mode")
        
        # Strict: Should error
        report = loader.validate_scene(scene_data, strict=True)
        self.assertFalse(report.ok, "Strict validation should fail")
        self.assertTrue(any("unknown field 'unknown_field'" in e for e in report.errors),
                        "Should error about unknown field in strict mode")

    def test_known_extra_fields(self):
        """Ensure known extra fields pass strict validation."""
        loader = SceneLoader()
        scene_data = {
            "name": "Test Scene",
            "entities": [
                {
                    "name": "Player",
                    "x": 0,
                    "y": 0,
                    "tag": "player",
                    "spawn_id": "start"
                }
            ]
        }
        
        report = loader.validate_scene(scene_data, strict=True)
        self.assertTrue(report.ok, "Known extra fields should pass strict validation")
