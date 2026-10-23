"""Loading says so: every successful load confirms; a failed one never claims success.

(Until Milestone 11 reloading the same save said nothing; the file name is kept from that earlier policy.)
"""

import json
import unittest
from unittest.mock import MagicMock

from engine.save_manager import SaveManager


class TestLoadedToast(unittest.TestCase):
    def setUp(self):
        self.mock_window = MagicMock()
        self.mock_window.scene_controller = MagicMock()
        self.mock_window.game_state_controller = MagicMock()
        self.mock_window.ui_controller = MagicMock()
        self.mock_window.player_hud = MagicMock()

        self.save_manager = SaveManager(self.mock_window, save_dir="tests/temp_saves_idempotent")
        if not self.save_manager.save_dir.exists():
            self.save_manager.save_dir.mkdir(parents=True)

    def tearDown(self):
        if self.save_manager.save_dir.exists():
            for f in self.save_manager.save_dir.glob("*"):
                f.unlink()
            self.save_manager.save_dir.rmdir()

    def _write(self, slot: str) -> None:
        with open(self.save_manager.get_save_path(slot), "w") as f:
            json.dump({"game_state": {"level": 1}, "meta": {"scene_path": "scenes/test.json"}}, f)

    def test_every_load_is_confirmed(self):
        self._write("slot1")
        self._write("slot2")
        for slot in ("slot1", "slot1", "slot2"):  # the same save twice, then another
            self.mock_window.player_hud.enqueue_toast.reset_mock()
            self.assertTrue(self.save_manager.load_game(slot))
            self.mock_window.player_hud.enqueue_toast.assert_called_once_with("Game loaded")

    def test_a_failed_load_never_claims_success(self):
        self.save_manager.load_game("non_existent")
        toasts = [c.args[0] for c in self.mock_window.player_hud.enqueue_toast.call_args_list]
        self.assertNotIn("Game loaded", toasts)
