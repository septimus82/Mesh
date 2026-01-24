import unittest
from unittest.mock import MagicMock
from engine.console_controller import ConsoleController

class TestEncounterRerollDeterminism(unittest.TestCase):
    def setUp(self):
        self.mock_window = MagicMock()
        self.mock_window.engine_config.profile = "dev"
        self.mock_window.scene_controller.scene_settings = {"encounter_seed": 123}
        self.mock_window.scene_controller.current_scene_id = "test_scene"
        self.console = ConsoleController(self.mock_window)
        self.console.log = MagicMock()

    def test_reroll_explicit_seed(self):
        self.console._encounter_command(["reroll", "555"])
        self.assertEqual(self.mock_window.scene_controller.scene_settings["encounter_seed"], 555)

    def test_reroll_no_seed_resets_to_canonical(self):
        # If seed exists in settings, it should be overwritten by the canonical scene hash
        # This ensures 'reroll' without args always returns to a known deterministic state
        expected_seed = sum(ord(c) for c in "test_scene") * 12345 % 1000000
        self.console._encounter_command(["reroll"])
        self.assertEqual(self.mock_window.scene_controller.scene_settings["encounter_seed"], expected_seed)

    def test_reroll_fallback_hash(self):
        # If no seed in settings, use hash of scene_id
        self.mock_window.scene_controller.scene_settings = {} # Clear seed
        self.console._encounter_command(["reroll"])
        
        seed = self.mock_window.scene_controller.scene_settings.get("encounter_seed")
        self.assertIsNotNone(seed)
        
        # Calculate expected hash
        scene_id = "test_scene"
        expected = sum(ord(c) for c in scene_id) * 12345 % 1000000
        self.assertEqual(seed, expected)
        
        # Verify stability
        self.mock_window.scene_controller.scene_settings = {}
        self.console._encounter_command(["reroll"])
        self.assertEqual(self.mock_window.scene_controller.scene_settings["encounter_seed"], expected)

if __name__ == "__main__":
    unittest.main()
