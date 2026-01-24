import pytest
from unittest.mock import MagicMock
from engine.ui import PaletteOverlay
from engine.palette_mode import get_state

def test_overlay_formatting():
    window = MagicMock()
    overlay = PaletteOverlay(window)
    
    state = get_state()
    state.reset()
    state.enabled = True
    state.mode = "STAMPS"
    state.selected_index = 0
    state.stamps = [] # Empty
    
    try:
        # Mock window props
        window.camera_controller.camera_x = 0
        window.camera_controller.camera_y = 0
        window.input_controller.mouse_x = 0
        window.input_controller.mouse_y = 0
        
        lines = overlay.get_lines()
        assert "PALETTE: ON STAMPS" in lines
        assert "selected=<none>" in lines
        assert "index=0/0" in lines
        assert "hover=(0,0) layer=ground" in lines
        assert "last_saved=<none>" in lines
    finally:
        state.reset()
