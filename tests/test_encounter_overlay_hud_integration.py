from unittest.mock import MagicMock, patch

import pytest

from engine.game import GameWindow

pytestmark = [pytest.mark.integration, pytest.mark.slow]

@pytest.fixture
def mock_window():
    # Mock GameWindow to avoid real window creation
    # We mock the class itself so instantiation returns a mock or manageable object
    # But the test tries to access logic within GameWindow.
    # It's better to patch the window creation internals if possible, or use a dummy window.
    # Given the test logic expects 'draw_debug_overlay' to be real, we can't fully mock GameWindow.
    # We must allow GameWindow logic but mock its dependencies (pyscreen, ctx, etc).
    # But GameWindow() calls a lot of arcade init.

    # Alternative: Subclass or Mock instantiation
    with patch("engine.game.GameWindow.__init__", return_value=None):
        window = GameWindow(800, 600, "Test")
        # Mock set_size and get_size to avoid calculation errors
        window.set_size = MagicMock()
        window.get_size = MagicMock(return_value=(800, 600))
        
        # Manually set attributes that __init__ would set
        window.width = 800
        window.height = 600
        window.engine_config = MagicMock()
        window.engine_config.debug_mode = True
        window.engine_config.debug_page = 0
        window.scene_controller = MagicMock()
        window.scene_controller.scene_settings = {}
        window.text_cache = MagicMock()
        window._debug_text = MagicMock()
        window.event_bus = MagicMock()
        
        mock_draw = MagicMock()
        with patch("engine.text_draw.draw_text_cached", mock_draw):
            yield window, mock_draw

def test_overlay_draws_when_enabled(mock_window):
    window, mock_draw_text = mock_window
    window.text_cache = None
    window.encounter_debug_overlay = True

    # Mock the helper to return specific lines
    with patch("engine.encounter_debug.get_encounter_debug_lines", return_value=["EncLine1", "EncLine2"]):
        window.draw_debug_overlay()

    # Check if draw_text was called with our lines
    calls = [args[0] for args, _ in mock_draw_text.call_args_list]
    assert "EncLine1" in calls
    assert "EncLine2" in calls

def test_overlay_hidden_when_disabled(mock_window):
    window, mock_draw_text = mock_window
    window.encounter_debug_overlay = False
    
    with patch("engine.encounter_debug.get_encounter_debug_lines", return_value=["EncLine1"]):
        window.draw_debug_overlay()
        
    calls = [args[0] for args, _ in mock_draw_text.call_args_list]
    assert "EncLine1" not in calls
