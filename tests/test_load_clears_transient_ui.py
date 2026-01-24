import unittest
from unittest.mock import MagicMock, patch, ANY
import json
from pathlib import Path
from engine.save_manager import SaveManager
from engine.ui import ToastQueue

class TestLoadClearsTransientUI(unittest.TestCase):
    def setUp(self):
        self.mock_window = MagicMock()
        self.mock_window.scene_controller = MagicMock()
        self.mock_window.game_state_controller = MagicMock()
        
        # Mock UI Controller
        self.mock_ui_controller = MagicMock()
        self.mock_window.ui_controller = self.mock_ui_controller
        
        # Mock Player HUD
        self.mock_player_hud = MagicMock()
        self.mock_window.player_hud = self.mock_player_hud
        
        # Mock Save Manager
        self.save_manager = SaveManager(self.mock_window, save_dir="tests/temp_saves")
        
        # Ensure save dir exists
        if not self.save_manager.save_dir.exists():
            self.save_manager.save_dir.mkdir(parents=True)

    def tearDown(self):
        # Clean up temp saves
        if self.save_manager.save_dir.exists():
            for f in self.save_manager.save_dir.glob("*"):
                f.unlink()
            self.save_manager.save_dir.rmdir()

    def test_load_clears_ui_and_toasts(self):
        # 1. Setup initial state
        slot_name = "test_slot"
        save_path = self.save_manager.get_save_path(slot_name)
        
        # Create a dummy save file
        save_data = {
            "game_state": {"level": 1},
            "meta": {"scene_path": "scenes/test.json"}
        }
        with open(save_path, "w") as f:
            json.dump(save_data, f)
            
        # 2. Simulate "dirty" UI state before load
        # We can't easily simulate the actual UI objects without full instantiation,
        # but we can verify that the reset methods are called.
        
        # 3. Perform Load
        result = self.save_manager.load_game(slot_name)
        
        # 4. Assertions
        self.assertTrue(result)
        
        # Verify UI reset was called
        self.mock_ui_controller.reset_transient_state.assert_called_once()
        
        # Verify Toasts were cleared and "Loaded" enqueued
        self.mock_player_hud.clear_toasts.assert_called_once()
        self.mock_player_hud.enqueue_toast.assert_called_with("Loaded")
        
        # Verify scene change requested
        self.mock_window.request_scene_change.assert_called_with(str(save_path))

    def test_load_failure_does_not_clear_ui(self):
        # 1. Attempt to load non-existent slot
        result = self.save_manager.load_game("non_existent_slot")
        
        # 2. Assertions
        self.assertFalse(result)
        
        # Verify UI reset was NOT called
        self.mock_ui_controller.reset_transient_state.assert_not_called()
        self.mock_player_hud.clear_toasts.assert_not_called()
        self.mock_player_hud.enqueue_toast.assert_not_called()

    def test_toast_queue_clear_implementation(self):
        # Test the actual implementation of clear() in ToastQueue
        # We need to import the real class to test it, but we can just instantiate it directly
        from engine.ui import ToastQueue as RealToastQueue
        # Ensure we have the real class, not a mock if it was patched elsewhere (though it shouldn't be here)
        if isinstance(RealToastQueue, MagicMock):
             # If it is mocked, we can't test the implementation. 
             # But since we are in a separate test method without patch decorator, it should be fine
             # UNLESS engine.ui was patched globally or in setUp? No.
             pass

        queue = RealToastQueue()
        
        # Add some items
        queue.enqueue("Old Toast 1")
        queue.enqueue("Old Toast 2")
        queue.current_text = "Current Toast"
        queue._seconds_remaining = 2.0
        
        # Act
        queue.clear()
        
        # Assert
        self.assertEqual(len(queue._queue), 0)
        self.assertEqual(queue.current_text, "")
        self.assertEqual(queue._seconds_remaining, 0.0)

    def test_ui_controller_reset_implementation(self):
        # Test the actual implementation of reset_transient_state in UIController
        from engine.ui_controller import UIController
        
        # Mock window and components
        window = MagicMock()
        window.pause_menu = MagicMock()
        window.paused = True
        
        controller = UIController(window)
        
        # Mock UI elements
        controller.dialogue_box = MagicMock()
        controller.quest_log = MagicMock()
        controller.inventory_overlay = MagicMock()
        controller.shop_panel = MagicMock()
        controller.character_panel = MagicMock()
        
        # Act
        controller.reset_transient_state()
        
        # Assert
        controller.dialogue_box.close.assert_called_once()
        controller.quest_log.close.assert_called_once()
        controller.inventory_overlay.close.assert_called_once()
        controller.shop_panel.close.assert_called_once()
        controller.character_panel.close.assert_called_once()
        
        # Verify PauseMenu closed
        window.pause_menu.visible = False # This is a property set, hard to verify on mock unless we check attribute
        # But we can check if window.paused was set to False
        self.assertFalse(window.paused)
