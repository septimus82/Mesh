import unittest
from engine.config import load_config

class TestPresetsRequiredExist(unittest.TestCase):
    def test_required_presets_exist(self):
        """Ensure critical presets are present in the configuration."""
        config = load_config()
        presets = getattr(config, "presets", {})
        
        required_presets = [
            "ci-check",
            "encounter-ci",
            "encounter-balance-sweep",
            "encounter-ci-diff"
        ]
        
        for preset in required_presets:
            self.assertIn(preset, presets, f"Required preset '{preset}' is missing from config.json")
