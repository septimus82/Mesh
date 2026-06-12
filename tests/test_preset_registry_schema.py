import unittest

from engine.config import load_config


class TestPresetRegistrySchema(unittest.TestCase):
    def test_presets_have_valid_schema(self):
        """Ensure all presets follow the standardized schema."""
        config = load_config()
        presets = getattr(config, "presets", {})

        for name, preset in presets.items():
            with self.subTest(preset=name):
                # Must be a dict (we standardized this)
                self.assertIsInstance(preset, dict, f"Preset '{name}' must be a dictionary")

                # Must have a description
                self.assertIn("description", preset, f"Preset '{name}' missing 'description'")
                self.assertIsInstance(preset["description"], str, f"Preset '{name}' description must be a string")
                self.assertTrue(preset["description"].strip(), f"Preset '{name}' description cannot be empty")

                # Optional lighting_showcase boolean
                if "lighting_showcase" in preset:
                    self.assertIsInstance(preset["lighting_showcase"], bool, f"Preset '{name}' lighting_showcase must be a boolean")

                # Must have either 'steps' or 'action'
                has_steps = "steps" in preset
                has_action = "action" in preset
                self.assertTrue(has_steps or has_action, f"Preset '{name}' must have 'steps' or 'action'")

                if has_steps:
                    steps = preset["steps"]
                    self.assertIsInstance(steps, list, f"Preset '{name}' steps must be a list")
                    self.assertTrue(steps, f"Preset '{name}' steps cannot be empty")

                    for i, step in enumerate(steps):
                        self.assertIsInstance(step, dict, f"Preset '{name}' step {i} must be a dict")
                        self.assertIn("cmd", step, f"Preset '{name}' step {i} missing 'cmd'")
                        self.assertIsInstance(step["cmd"], str, f"Preset '{name}' step {i} 'cmd' must be a string")

                        if "args" in step:
                            self.assertIsInstance(step["args"], list, f"Preset '{name}' step {i} 'args' must be a list")
                            for arg in step["args"]:
                                self.assertIsInstance(arg, str, f"Preset '{name}' step {i} arg must be a string")

                if has_action:
                    self.assertIsInstance(preset["action"], str, f"Preset '{name}' action must be a string")
                    if "args" in preset:
                        self.assertIsInstance(preset["args"], dict, f"Preset '{name}' action args must be a dict")

if __name__ == "__main__":
    unittest.main()
