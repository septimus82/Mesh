import json
import time
import unittest
from unittest.mock import MagicMock

from engine.save_manager import SaveManager


class TestLoadedToastIdempotent(unittest.TestCase):
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

    def test_loaded_toast_is_idempotent(self):
        # 1. Create a save file
        slot_name = "test_slot"
        save_path = self.save_manager.get_save_path(slot_name)
        save_data = {"game_state": {"level": 1}, "meta": {"scene_path": "scenes/test.json"}}
        with open(save_path, "w") as f:
            json.dump(save_data, f)

        # 2. First Load: Should show "Loaded"
        self.save_manager.load_game(slot_name)
        self.mock_window.player_hud.enqueue_toast.assert_called_with("Loaded")
        self.mock_window.player_hud.enqueue_toast.reset_mock()

        # 3. Second Load (same file, no change): Should NOT show "Loaded"
        self.save_manager.load_game(slot_name)
        self.mock_window.player_hud.enqueue_toast.assert_not_called()

        # 4. Modify file (update mtime)
        # Wait a tiny bit to ensure mtime changes (though st_mtime_ns should be fine)
        time.sleep(0.01)
        save_path.touch()

        # 5. Third Load (modified file): Should show "Loaded"
        self.save_manager.load_game(slot_name)
        self.mock_window.player_hud.enqueue_toast.assert_called_with("Loaded")
        self.mock_window.player_hud.enqueue_toast.reset_mock()

    def test_switching_slots_shows_toast(self):
        # 1. Create two save files
        slot1 = "slot1"
        slot2 = "slot2"
        path1 = self.save_manager.get_save_path(slot1)
        path2 = self.save_manager.get_save_path(slot2)

        with open(path1, "w") as f:
            json.dump({}, f)
        with open(path2, "w") as f:
            json.dump({}, f)

        # 2. Load Slot 1 -> Toast
        self.save_manager.load_game(slot1)
        self.mock_window.player_hud.enqueue_toast.assert_called_with("Loaded")
        self.mock_window.player_hud.enqueue_toast.reset_mock()

        # 3. Load Slot 2 -> Toast
        self.save_manager.load_game(slot2)
        self.mock_window.player_hud.enqueue_toast.assert_called_with("Loaded")
        self.mock_window.player_hud.enqueue_toast.reset_mock()

        # 4. Load Slot 1 again -> Toast (different from last load)
        self.save_manager.load_game(slot1)
        self.mock_window.player_hud.enqueue_toast.assert_called_with("Loaded")

    def test_load_failure_does_not_update_signature(self):
        # 1. Create save
        slot = "slot_fail"
        path = self.save_manager.get_save_path(slot)
        with open(path, "w") as f:
            json.dump({}, f)

        # 2. Load successfully
        self.save_manager.load_game(slot)
        self.mock_window.player_hud.enqueue_toast.assert_called_with("Loaded")
        self.mock_window.player_hud.enqueue_toast.reset_mock()

        # 3. Try to load non-existent slot (fails)
        self.save_manager.load_game("non_existent")
        self.mock_window.player_hud.enqueue_toast.assert_not_called()

        # 4. Load original slot again (same file) -> Should NOT toast because signature matches last SUCCESSFUL load
        self.save_manager.load_game(slot)
        self.mock_window.player_hud.enqueue_toast.assert_not_called()
