import pytest
import engine.optional_arcade as optional_arcade
from unittest.mock import MagicMock
from engine.scene_controller import SceneController

def test_arcade_window_harness_guard(mock_arcade_window, mock_arcade_background):
    """
    Guard test to ensure shared fixtures correctly prevent real window access.
    
    Without these fixtures, SceneController instantiation or usage would raise 
    RuntimeError (No window is active) or attempt to access the real window.
    """
    # 1. Verify get_window returns a mock
    window = optional_arcade.arcade.get_window()
    assert isinstance(window, MagicMock)
    
    # 2. Verify set_background_color is mocked (no-op)
    optional_arcade.arcade.set_background_color(optional_arcade.arcade.color.BLACK)
    
    # 3. Verify SceneController instantiation (which accesses get_window internally)
    # We need to populate the mock window with expected attributes for SceneController
    window.width = 800
    window.height = 600
    window.ctx = MagicMock()
    window.scene_loader = MagicMock()
    window.lighting = MagicMock()
    window.ui_controller = MagicMock()
    window.camera_controller = MagicMock()
    window.audio = MagicMock()
    window.quest_manager = MagicMock()
    window.game_state = MagicMock()
    window.input_controller = MagicMock()
    window.assets = MagicMock()
    
    # SceneController.__init__ creates SpriteLists which call optional_arcade.arcade.get_window()
    controller = SceneController(window)
    assert controller is not None
