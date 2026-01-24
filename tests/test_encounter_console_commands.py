import unittest
from unittest.mock import MagicMock, patch
from engine.console_controller import ConsoleController

class TestEncounterConsoleCommands(unittest.TestCase):
    def setUp(self):
        self.mock_window = MagicMock()
        self.mock_window.engine_config.profile = "dev"
        self.mock_window.scene_controller.scene_settings = {}
        self.console = ConsoleController(self.mock_window)
        self.console.log = MagicMock()

    def test_profile_check(self):
        self.mock_window.engine_config.profile = "release"
        self.console._encounter_command(["show"])
        self.console.log.assert_called_with("Error: Encounter commands are dev-only (profile != dev).")

    def test_show_command(self):
        with patch("engine.encounter_debug.get_encounter_debug_lines") as mock_get_lines:
            mock_get_lines.return_value = ["Line 1", "Line 2"]
            self.console._encounter_command(["show"])
            self.console.log.assert_any_call("Line 1")
            self.console.log.assert_any_call("Line 2")

    def test_reroll_command(self):
        # Test explicit seed
        self.console._encounter_command(["reroll", "123"])
        self.assertEqual(self.mock_window.scene_controller.scene_settings["encounter_seed"], 123)
        self.mock_window.request_scene_reload.assert_called()
        
        # Test deterministic fallback
        self.mock_window.scene_controller.current_scene_id = "test_scene"
        expected_seed = sum(ord(c) for c in "test_scene") * 12345 % 1000000
        self.console._encounter_command(["reroll"])
        self.assertEqual(self.mock_window.scene_controller.scene_settings["encounter_seed"], expected_seed)

    def test_set_difficulty(self):
        self.console._encounter_command(["set-difficulty", "hard"])
        self.assertEqual(self.mock_window.scene_controller.scene_settings["encounter_budget_profile"], "hard")
        self.mock_window.request_scene_reload.assert_called()

    def test_set_budget(self):
        self.console._encounter_command(["set-budget", "2000"])
        self.assertEqual(self.mock_window.scene_controller.scene_settings["encounter_budget"], 2000)
        self.mock_window.request_scene_reload.assert_called()

    def test_set_layout(self):
        self.console._encounter_command(["set-layout", "gauntlet"])
        self.assertEqual(self.mock_window.scene_controller.scene_settings["encounter_layout"], "gauntlet")
        self.mock_window.request_scene_reload.assert_called()
