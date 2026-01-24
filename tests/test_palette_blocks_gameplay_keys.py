import pytest
import arcade
from unittest.mock import MagicMock
from engine.input_runtime.capture import handle_key_press
from engine.palette_mode import get_state, toggle_palette

def test_palette_blocks_gameplay_keys():
    controller = MagicMock()
    controller.window.console_controller.active = False
    controller.window.ui_controller.on_key_press.return_value = False
    controller.window.editor_controller.active = False
    
    state = get_state()
    state.reset()
    state.enabled = True
    
    try:
        # E should be blocked (return True)
        assert handle_key_press(controller, arcade.key.E, 0) is True
        
        # Space should be blocked
        assert handle_key_press(controller, arcade.key.SPACE, 0) is True
        
        # F3 should be handled (return True)
        assert handle_key_press(controller, arcade.key.F3, 0) is True
        
        # WASD should NOT be blocked (return False)
        # Assuming they are not mapped to palette keys
        assert handle_key_press(controller, arcade.key.W, 0) is False
    finally:
        state.reset()
