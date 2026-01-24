import unittest
from unittest.mock import MagicMock, patch
import os
from engine.input_controller import InputController

class TestVariantDFirstInputToast(unittest.TestCase):
    def setUp(self):
        self.mock_window = MagicMock()
        self.mock_window.ui_controller = MagicMock()
        self.mock_window.ui_controller.input_blocked = False
        self.mock_window.player_hud = MagicMock()
        
        self.patcher_manager = patch("engine.input_controller.InputManager")
        self.MockInputManager = self.patcher_manager.start()
        self.mock_manager = self.MockInputManager.return_value
        self.mock_manager.get_bound_action_names.return_value = []
        
        self.patcher_dispatch = patch("engine.input_controller.dispatch_action")
        self.mock_dispatch = self.patcher_dispatch.start()
        self.mock_dispatch.return_value = True
        
        self.patcher_bindings = patch("engine.input_controller.InputController._load_configured_bindings")
        self.patcher_bindings.start()

    def tearDown(self):
        self.patcher_manager.stop()
        self.patcher_dispatch.stop()
        self.patcher_bindings.stop()
        if "MESH_ACTIVE_PRESET" in os.environ:
            del os.environ["MESH_ACTIVE_PRESET"]

    def test_toast_fires_on_gameplay_action_variant_d(self):
        os.environ["MESH_ACTIVE_PRESET"] = "golden_slice_variant_d"
        controller = InputController(self.mock_window)
        
        # Setup: "move_right" is pressed
        self.mock_manager.get_bound_action_names.return_value = ["move_right"]
        self.mock_manager.was_action_pressed.side_effect = lambda action: action == "move_right"
        
        # Act
        controller.update(0.1)
        
        # Assert
        self.mock_window.player_hud.enqueue_toast.assert_called_once_with("GO!")
        self.mock_dispatch.assert_called_with(self.mock_window, "move_right")

    def test_toast_does_not_fire_on_other_presets(self):
        os.environ["MESH_ACTIVE_PRESET"] = "other_preset"
        controller = InputController(self.mock_window)
        
        self.mock_manager.get_bound_action_names.return_value = ["move_right"]
        self.mock_manager.was_action_pressed.side_effect = lambda action: action == "move_right"
        
        controller.update(0.1)
        
        self.mock_window.player_hud.enqueue_toast.assert_not_called()

    def test_toast_does_not_fire_on_system_action(self):
        os.environ["MESH_ACTIVE_PRESET"] = "golden_slice_variant_d"
        controller = InputController(self.mock_window)
        
        # Setup: "toggle_help" is pressed (system action)
        self.mock_manager.get_bound_action_names.return_value = ["toggle_help"]
        self.mock_manager.was_action_pressed.side_effect = lambda action: action == "toggle_help"
        
        controller.update(0.1)
        
        self.mock_window.player_hud.enqueue_toast.assert_not_called()
        self.mock_dispatch.assert_called_with(self.mock_window, "toggle_help")

    def test_toast_fires_only_once(self):
        os.environ["MESH_ACTIVE_PRESET"] = "golden_slice_variant_d"
        controller = InputController(self.mock_window)
        
        self.mock_manager.get_bound_action_names.return_value = ["move_right"]
        self.mock_manager.was_action_pressed.side_effect = lambda action: action == "move_right"
        
        # First update
        controller.update(0.1)
        self.mock_window.player_hud.enqueue_toast.assert_called_once_with("GO!")
        self.mock_window.player_hud.enqueue_toast.reset_mock()
        
        # Second update
        controller.update(0.1)
        self.mock_window.player_hud.enqueue_toast.assert_not_called()

    def test_toast_does_not_fire_if_input_blocked(self):
        os.environ["MESH_ACTIVE_PRESET"] = "golden_slice_variant_d"
        controller = InputController(self.mock_window)
        
        self.mock_window.ui_controller.input_blocked = True
        self.mock_manager.get_bound_action_names.return_value = ["move_right"]
        self.mock_manager.was_action_pressed.side_effect = lambda action: action == "move_right"
        
        controller.update(0.1)
        
        self.mock_window.player_hud.enqueue_toast.assert_not_called()
        # Dispatch should not be called for gameplay action when blocked
        self.mock_dispatch.assert_not_called()

    def test_toast_does_not_fire_if_input_blocked_but_system_action_allowed(self):
        os.environ["MESH_ACTIVE_PRESET"] = "golden_slice_variant_d"
        controller = InputController(self.mock_window)
        
        self.mock_window.ui_controller.input_blocked = True
        # "toggle_help" is in ACTIONS_ALLOWED_WHEN_BLOCKED
        self.mock_manager.get_bound_action_names.return_value = ["toggle_help"]
        self.mock_manager.was_action_pressed.side_effect = lambda action: action == "toggle_help"
        
        controller.update(0.1)
        
        self.mock_window.player_hud.enqueue_toast.assert_not_called()
        self.mock_dispatch.assert_called_with(self.mock_window, "toggle_help")
