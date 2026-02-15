import unittest
from unittest.mock import MagicMock, patch
from engine.console_controller import ConsoleController
from engine.console_runtime.commands import dispatch_command

class TestEncounterDevOnlyGuard(unittest.TestCase):
    def setUp(self):
        self.mock_window = MagicMock()
        self.mock_window.engine_config = MagicMock()
        self.mock_window.engine_config.profile = "release"  # Default to non-dev
        self.mock_window.encounter_debug_overlay = False # Initialize to False
        self.console = ConsoleController(self.mock_window)
        self.console.log = MagicMock()

    def _dispatch_encounter(self, args):
        dispatch_command(self.console, "encounter", args)

    def test_reroll_blocked_in_release(self):
        self._dispatch_encounter(["reroll"])
        self.console.log.assert_called_with("Error: Encounter commands are dev-only (profile != dev).")
        self.mock_window.reload_scene.assert_not_called()

    def test_overlay_blocked_in_release(self):
        self._dispatch_encounter(["overlay"])
        self.console.log.assert_called_with("Error: Encounter commands are dev-only (profile != dev).")
        # Ensure overlay flag wasn't toggled (assuming it starts False/None)
        self.assertFalse(getattr(self.mock_window, "encounter_debug_overlay", False))

    def test_set_budget_blocked_in_release(self):
        self._dispatch_encounter(["set-budget", "1000"])
        self.console.log.assert_called_with("Error: Encounter commands are dev-only (profile != dev).")
        # Ensure no settings changed (mock scene_controller)
        # Since we didn't set up scene_controller mock deeply, just checking the log and return is enough
        # as the code returns early.

    def test_allowed_in_dev(self):
        self.mock_window.engine_config.profile = "dev"
        self.mock_window.scene_controller.scene_settings = {}
        
        # Reroll should proceed
        self._dispatch_encounter(["reroll"])
        # Should log "Rerolling..." not "Error..."
        args, _ = self.console.log.call_args
        self.assertTrue(args[0].startswith("Rerolling encounters"))

if __name__ == "__main__":
    unittest.main()
