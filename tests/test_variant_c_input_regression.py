
import unittest
from unittest.mock import MagicMock, patch
import arcade
from engine.ui_controller import UIController
from engine.input_controller import InputController
from engine.ui import UIElement

class MockGameWindow:
    def __init__(self):
        self.ui_controller = None
        self.input_controller = None
        self.console_controller = MagicMock()
        self.console_controller.active = False  # Ensure console is not active by default
        self.console_controller.process_key = MagicMock(return_value=False)
        self.editor_controller = MagicMock()
        self.editor_controller.active = False
        self.editor_controller.panels = None
        self.editor_controller.ui_layers = None
        self.editor_controller.keybinds = None
        self.editor_controller.project_explorer = None
        self.engine_config = MagicMock()
        self.engine_config.player_stats_enabled = True
        self.game_state_controller = MagicMock()
        self.show_debug = False
        self.command_palette_enabled = False
        self.settings_overlay = None
        self.width = 800
        self.height = 600
        
    def _toggle_paused_state(self):
        return False
        
    def console_log(self, msg):
        pass

class TestVariantCInputRegression(unittest.TestCase):
    def setUp(self):
        self.window = MockGameWindow()
        
        # Initialize controllers manually
        self.window.ui_controller = UIController(self.window)
        self.window.input_controller = InputController(self.window)
        
    def test_not_blocked_on_start(self):
        """Assert ui_controller.input_blocked is False after init."""
        # Check if input is blocked
        is_blocked = self.window.ui_controller.input_blocked
        
        # If it is blocked, find out why
        if is_blocked:
            blocking_elements = [
                e.__class__.__name__ 
                for e in self.window.ui_controller.ui_elements 
                if getattr(e, "blocks_input", False)
            ]
            print(f"Blocking elements: {blocking_elements}")
            
        self.assertFalse(is_blocked, "Input should not be blocked on start")

    def test_movement_dispatch_works_when_unblocked(self):
        """Simulate a bound movement action and assert dispatch."""
        # Mock dispatch_action to verify it gets called
        with patch('engine.input_controller.dispatch_action', return_value=True) as mock_dispatch:
            # Mock InputManager to simulate key press
            self.window.input_controller.manager.was_action_pressed = MagicMock(return_value=False)
            self.window.input_controller.manager.get_bound_action_names = MagicMock(return_value=["move_up"])
            
            # Simulate update
            self.window.input_controller.update(0.016)
            
            # Should not be called yet
            mock_dispatch.assert_not_called()
            
            # Now simulate press
            self.window.input_controller.manager.was_action_pressed = MagicMock(
                side_effect=lambda action: action == "move_up"
            )
            
            self.window.input_controller.update(0.016)
            
            mock_dispatch.assert_called_with(self.window, "move_up")

    def test_blocked_ui_can_be_dismissed(self):
        """Ensure blocked UI can be dismissed."""
        # Create a dummy blocking UI element
        class BlockingUI(UIElement):
            def __init__(self, window):
                super().__init__(window)
                self.visible = True
                
            @property
            def blocks_input(self):
                return self.visible
                
            def on_key_press(self, key, modifiers):
                if key == arcade.key.ESCAPE:
                    self.visible = False
                    return True
                return False

        blocking_ui = BlockingUI(self.window)
        self.window.ui_controller.register_ui_element(blocking_ui)
        
        self.assertTrue(self.window.ui_controller.input_blocked)
        
        # Simulate ESC key press
        # We need to call window.on_key_press or input_controller.on_key_press
        # GameWindow delegates to InputController, which delegates to UIController
        
        # Use real arcade.key.ESCAPE
        handled = self.window.input_controller.on_key_press(arcade.key.ESCAPE, 0)
        self.assertTrue(handled)
        self.assertFalse(blocking_ui.visible)
        self.assertFalse(self.window.ui_controller.input_blocked)

    def test_whitelisted_action_dispatches_when_blocked(self):
        """Ensure whitelisted actions dispatch even when input is blocked."""
        # Create a blocking UI that relies on an action to close (like CharacterPanel)
        class BlockingActionUI(UIElement):
            def __init__(self, window):
                super().__init__(window)
                self.visible = True
                
            @property
            def blocks_input(self):
                return self.visible

        blocking_ui = BlockingActionUI(self.window)
        self.window.ui_controller.register_ui_element(blocking_ui)
        self.assertTrue(self.window.ui_controller.input_blocked)
        
        # Mock dispatch_action
        with patch('engine.input_controller.dispatch_action', return_value=True) as mock_dispatch:
            # Mock InputManager
            self.window.input_controller.manager.was_action_pressed = MagicMock(
                side_effect=lambda action: action == "show_character"
            )
            self.window.input_controller.manager.get_bound_action_names = MagicMock(
                return_value=["show_character", "move_up"]
            )
            
            # Update
            self.window.input_controller.update(0.016)
            
            # show_character should be dispatched (whitelisted)
            mock_dispatch.assert_any_call(self.window, "show_character")
            
            # move_up should NOT be dispatched (blocked)
            with self.assertRaises(AssertionError):
                mock_dispatch.assert_any_call(self.window, "move_up")

if __name__ == '__main__':
    unittest.main()
