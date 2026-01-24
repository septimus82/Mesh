import pytest
from unittest.mock import MagicMock, patch
from engine.editor_controller import EditorModeController
from engine.config import EngineConfig
import arcade

class MockWindow:
    def __init__(self):
        cfg = EngineConfig()
        self.width = cfg.width
        self.height = cfg.height
        self.paused = False
        self.scene_controller = MagicMock()
        self.screen_to_world = MagicMock(return_value=(100, 100))
        # Mock ensure methods for inspector
        self.scene_controller._ensure_entity_data_dict.return_value = {}
        self.scene_controller._ensure_behaviour_config_root.return_value = {}
        self.scene_controller._get_behaviour_configs_for_sprite.return_value = []

def test_inspector_activation():
    window = MockWindow()
    controller = EditorModeController(window)
    controller.active = True
    
    # Select an entity
    sprite = MagicMock(spec=arcade.Sprite)
    sprite.mesh_behaviours = []
    controller.selected_entity = sprite
    
    # Press TAB to activate inspector
    controller.handle_input(arcade.key.TAB, 0)
    assert controller.inspector_active
    
    # Press TAB again to deactivate
    controller.handle_input(arcade.key.TAB, 0)
    assert not controller.inspector_active

def test_inspector_navigation():
    window = MockWindow()
    controller = EditorModeController(window)
    controller.active = True
    controller.inspector_active = True
    
    sprite = MagicMock(spec=arcade.Sprite)
    sprite.mesh_behaviours = ["test_behaviour"]
    controller.selected_entity = sprite
    
    # Mock behaviour params
    with patch("engine.editor_controller.get_behaviour_param_defs") as mock_defs:
        mock_defs.return_value = {"param1": MagicMock(default=10, type=int)}
        
        # Build items
        items = controller._build_inspector_items()
        # Should have Entity Header, Behaviour Header, Param1
        assert len(items) == 3 
        
        # Mock cached items so navigation works
        controller._cached_inspector_items = items
        
        # Initial index
        assert controller.inspector_selection_index == 0
        
        # Down
        controller.handle_input(arcade.key.DOWN, 0)
        assert controller.inspector_selection_index == 1
        
        # Down again
        controller.handle_input(arcade.key.DOWN, 0)
        assert controller.inspector_selection_index == 2
        
        # Down at end (clamped)
        controller.handle_input(arcade.key.DOWN, 0)
        assert controller.inspector_selection_index == 2
        
        # Up
        controller.handle_input(arcade.key.UP, 0)
        assert controller.inspector_selection_index == 1

def test_inspector_edit_int():
    window = MockWindow()
    controller = EditorModeController(window)
    controller.active = True
    controller.inspector_active = True
    
    sprite = MagicMock(spec=arcade.Sprite)
    sprite.mesh_behaviours = ["test_behaviour"]
    controller.selected_entity = sprite
    
    # Mock behaviour params
    with patch("engine.editor_controller.get_behaviour_param_defs") as mock_defs:
        mock_defs.return_value = {"speed": MagicMock(default=10, type=int)}
        
        # Force items
        items = [
            {"type": "header", "text": "H1"},
            {"type": "header", "text": "H2"},
            {"type": "param", "name": "speed", "value": 10, "kind": "int", "behaviour": "test_behaviour", "is_default": True}
        ]
        controller._cached_inspector_items = items
        controller.inspector_selection_index = 2 # Select the param
        
        # Edit: Right arrow (+1)
        controller.handle_input(arcade.key.RIGHT, 0)
        
        # Verify update called
        # We need to check if _update_param logic works or mock it. 
        # Let's check the side effects on the window.scene_controller mocks
        
        # The controller should have tried to update the config
        # Since we mocked _ensure_behaviour_config_root to return a dict, we can check that dict
        config_root = window.scene_controller._ensure_behaviour_config_root.return_value
        # Wait, the _update_param calls _ensure... again.
        
        # Let's verify the value in the items was refreshed? 
        # Actually _update_param calls _refresh_inspector_items at the end.
        
        # Let's just verify the config dict was updated
        # The mock returns the SAME dict object every time
        assert config_root["test_behaviour"]["speed"] == 11

