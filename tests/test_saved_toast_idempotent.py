import unittest
from unittest.mock import MagicMock, patch
import json
from pathlib import Path
from engine.save_manager import SaveManager

class TestSavedToastIdempotent(unittest.TestCase):
    def setUp(self):
        self.mock_window = MagicMock()
        self.mock_window.scene_controller = MagicMock()
        # Use side_effect to return a fresh dict each time, otherwise 'meta' from previous save persists in the mock's return_value
        self.mock_window.scene_controller.build_scene_snapshot.side_effect = lambda compact=False: {"entities": []}
        self.mock_window.scene_controller.current_scene_path = "scenes/test.json"
        self.mock_window.game_state_controller = MagicMock()
        self.mock_window.game_state_controller.export_state.return_value = {"gold": 100}
        self.mock_window.player_hud = MagicMock()
        
        self.save_manager = SaveManager(self.mock_window, save_dir="tests/temp_saves_saved_idempotent")
        if not self.save_manager.save_dir.exists():
            self.save_manager.save_dir.mkdir(parents=True)

    def tearDown(self):
        if self.save_manager.save_dir.exists():
            for f in self.save_manager.save_dir.glob("*"):
                f.unlink()
            self.save_manager.save_dir.rmdir()

    def test_saved_toast_is_idempotent(self):
        slot = "test_slot"
        
        # 1. First Save -> Toast
        self.save_manager.save_game(slot)
        self.mock_window.player_hud.enqueue_toast.assert_called_with("Game Saved")
        self.mock_window.player_hud.enqueue_toast.reset_mock()
        
        # 2. Second Save (unchanged) -> No Toast
        self.save_manager.save_game(slot)
        self.mock_window.player_hud.enqueue_toast.assert_not_called()
        
        # 3. Mutate state -> Save -> Toast
        self.mock_window.game_state_controller.export_state.return_value = {"gold": 101}
        self.save_manager.save_game(slot)
        self.mock_window.player_hud.enqueue_toast.assert_called_with("Game Saved")
        self.mock_window.player_hud.enqueue_toast.reset_mock()
        
        # 4. Save again (unchanged) -> No Toast
        self.save_manager.save_game(slot)
        self.mock_window.player_hud.enqueue_toast.assert_not_called()

    def test_switching_slots_shows_toast(self):
        slot1 = "slot1"
        slot2 = "slot2"
        
        # 1. Save Slot 1 -> Toast
        self.save_manager.save_game(slot1)
        self.mock_window.player_hud.enqueue_toast.assert_called_with("Game Saved")
        self.mock_window.player_hud.enqueue_toast.reset_mock()
        
        # 2. Save Slot 2 (same content) -> Toast
        self.save_manager.save_game(slot2)
        self.mock_window.player_hud.enqueue_toast.assert_called_with("Game Saved")
        self.mock_window.player_hud.enqueue_toast.reset_mock()
        
        # 3. Save Slot 1 again -> Toast
        self.save_manager.save_game(slot1)
        self.mock_window.player_hud.enqueue_toast.assert_called_with("Game Saved")

    def test_save_failure_does_not_update_signature(self):
        slot = "slot_fail"
        
        # 1. Save successfully
        self.save_manager.save_game(slot)
        self.mock_window.player_hud.enqueue_toast.assert_called_with("Game Saved")
        self.mock_window.player_hud.enqueue_toast.reset_mock()
        
        # 2. Force failure (e.g. by making directory read-only or mocking open)
        with patch("pathlib.Path.open", side_effect=PermissionError("Mock error")):
            result = self.save_manager.save_game(slot)
            self.assertFalse(result)
            self.mock_window.player_hud.enqueue_toast.assert_not_called() # SaveManager doesn't toast failure
            
        # 3. Save successfully again (unchanged content) -> Should NOT toast because signature matches last SUCCESSFUL save
        # Wait, if the failure didn't update signature, the signature is still from step 1.
        # Content is unchanged. So it should match.
        self.save_manager.save_game(slot)
        self.mock_window.player_hud.enqueue_toast.assert_not_called()
