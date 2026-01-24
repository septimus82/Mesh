import unittest
from unittest.mock import MagicMock, patch
import json
from pathlib import Path

from engine.actions import ACTIONS
from engine.save_manager import SaveManager

class TestSaveQuickActions(unittest.TestCase):
    def setUp(self):
        self.window = MagicMock()
        self.window.player_hud = MagicMock()
        self.window.scene_controller = MagicMock()
        self.window.scene_controller.current_scene_path = "scenes/test.json"
        self.window.scene_controller.build_scene_snapshot.return_value = {"entities": []}
        self.window.game_state_controller = MagicMock()
        self.window.game_state_controller.export_state.return_value = {}
        
    def test_save_game_action_success(self):
        # Setup temp save dir
        with patch("engine.save_manager.Path") as mock_path:
            # We need a real temp dir for the save manager to write to, 
            # or we mock the open() call. 
            # Let's use a real temp dir via pytest fixture if possible, 
            # but this is unittest.TestCase.
            # We'll mock the SaveManager.save_game method to avoid file I/O complexity here,
            # relying on SaveManager tests for the actual saving logic.
            # The goal is to test the ACTION wiring.
            
            self.window.save_manager = MagicMock()
            self.window.save_manager.save_game.return_value = True
            
            action = ACTIONS["save_game"]
            action(self.window)
            
            self.window.save_manager.save_game.assert_called_with("quicksave")
            # Toast is now handled by SaveManager internally, not by the action wrapper
            self.window.player_hud.enqueue_toast.assert_not_called()

    def test_save_game_action_failure(self):
        self.window.save_manager = MagicMock()
        self.window.save_manager.save_game.return_value = False
        
        action = ACTIONS["save_game"]
        action(self.window)
        
        self.window.save_manager.save_game.assert_called_with("quicksave")
        self.window.player_hud.enqueue_toast.assert_called_with("Save Failed")

    def test_quickload_action_success(self):
        self.window.save_manager = MagicMock()
        self.window.save_manager.load_game.return_value = True
        
        action = ACTIONS["quickload_last_save"]
        action(self.window)
        
        self.window.save_manager.load_game.assert_called_with("quicksave")
        # Should NOT show toast on success (load usually changes scene/state immediately)
        self.window.player_hud.enqueue_toast.assert_not_called()

    def test_quickload_action_failure(self):
        self.window.save_manager = MagicMock()
        self.window.save_manager.load_game.return_value = False
        
        action = ACTIONS["quickload_last_save"]
        action(self.window)
        
        self.window.save_manager.load_game.assert_called_with("quicksave")
        self.window.player_hud.enqueue_toast.assert_called_with("No Save Found")

    def test_integration_with_real_save_manager(self):
        # Integration test with real SaveManager (using temp dir)
        import tempfile
        import shutil
        
        temp_dir = tempfile.mkdtemp()
        try:
            self.window.save_manager = SaveManager(self.window, save_dir=temp_dir)
            
            # 1. Try load (should fail)
            action_load = ACTIONS["quickload_last_save"]
            action_load(self.window)
            self.window.player_hud.enqueue_toast.assert_called_with("No Save Found")
            self.window.player_hud.enqueue_toast.reset_mock()
            
            # 2. Save
            action_save = ACTIONS["save_game"]
            action_save(self.window)
            self.window.player_hud.enqueue_toast.assert_called_with("Game Saved")
            self.window.player_hud.enqueue_toast.reset_mock()
            
            # Verify file exists
            save_path = Path(temp_dir) / "quicksave.json"
            self.assertTrue(save_path.exists())
            
            # 3. Load (should success)
            # Mock request_scene_change to avoid actual scene loading logic
            self.window.request_scene_change = MagicMock()
            
            action_load(self.window)
            self.window.request_scene_change.assert_called()
            self.window.player_hud.enqueue_toast.assert_called_with("Loaded")
            
        finally:
            shutil.rmtree(temp_dir)
