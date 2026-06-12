import unittest
from unittest.mock import MagicMock, patch

from engine.console_controller import ConsoleController
from engine.console_runtime.commands import dispatch_command


class TestEncounterConsoleCommands(unittest.TestCase):
    def setUp(self):
        self.mock_window = MagicMock()
        self.mock_window.engine_config.profile = "dev"
        self.mock_window.scene_controller.scene_settings = {}
        self.console = ConsoleController(self.mock_window)
        self.console.log = MagicMock()

    def _dispatch_encounter(self, args):
        dispatch_command(self.console, "encounter", args)

    def test_profile_check(self):
        self.mock_window.engine_config.profile = "release"
        self._dispatch_encounter(["show"])
        self.console.log.assert_called_with("Error: Encounter commands are dev-only (profile != dev).")

    def test_show_command(self):
        with patch("engine.encounter_debug.get_encounter_debug_lines") as mock_get_lines:
            mock_get_lines.return_value = ["Line 1", "Line 2"]
            self._dispatch_encounter(["show"])
            self.console.log.assert_any_call("Line 1")
            self.console.log.assert_any_call("Line 2")

    def test_reroll_command(self):
        # Test explicit seed
        self._dispatch_encounter(["reroll", "123"])
        self.assertEqual(self.mock_window.scene_controller.scene_settings["encounter_seed"], 123)
        self.mock_window.request_scene_reload.assert_called()

        # Test deterministic fallback
        self.mock_window.scene_controller.current_scene_id = "test_scene"
        expected_seed = sum(ord(c) for c in "test_scene") * 12345 % 1000000
        self._dispatch_encounter(["reroll"])
        self.assertEqual(self.mock_window.scene_controller.scene_settings["encounter_seed"], expected_seed)

    def test_set_difficulty(self):
        self._dispatch_encounter(["set-difficulty", "hard"])
        self.assertEqual(self.mock_window.scene_controller.scene_settings["encounter_budget_profile"], "hard")
        self.mock_window.request_scene_reload.assert_called()

    def test_set_budget(self):
        self._dispatch_encounter(["set-budget", "2000"])
        self.assertEqual(self.mock_window.scene_controller.scene_settings["encounter_budget"], 2000)
        self.mock_window.request_scene_reload.assert_called()

    def test_set_layout(self):
        self._dispatch_encounter(["set-layout", "gauntlet"])
        self.assertEqual(self.mock_window.scene_controller.scene_settings["encounter_layout"], "gauntlet")
        self.mock_window.request_scene_reload.assert_called()
