import os
import pytest
from unittest.mock import MagicMock, patch
from engine.lighting import LightManager
from engine.actions import _toggle_shadowmask

@pytest.fixture
def mock_window():
    window = MagicMock()
    window.player_hud = MagicMock()
    return window

@pytest.fixture
def light_manager(mock_window, mock_arcade_lighting):
    lm = LightManager(mock_window)
    lm.enabled = True
    lm._layer = MagicMock()
    lm._create_layer = MagicMock(return_value=lm._layer)
    mock_window.lighting = lm
    yield lm

def test_shadowmask_default_from_env(mock_window, mock_arcade_lighting):
    with patch.dict(os.environ, {"MESH_SHADOWCAST_MASK": "1"}):
        lm = LightManager(mock_window)
        assert lm.shadowmask_enabled is True
        
    with patch.dict(os.environ, {"MESH_SHADOWCAST_MASK": "0"}):
        lm = LightManager(mock_window)
        assert lm.shadowmask_enabled is False
        
    # Default off if missing
    if "MESH_SHADOWCAST_MASK" in os.environ:
        del os.environ["MESH_SHADOWCAST_MASK"]
    lm = LightManager(mock_window)
    assert lm.shadowmask_enabled is False

def test_toggle_shadowmask_action(light_manager, mock_window):
    # Start disabled
    light_manager.shadowmask_enabled = False
    
    # Toggle ON
    _toggle_shadowmask(mock_window)
    
    assert light_manager.shadowmask_enabled is True
    mock_window.player_hud.enqueue_toast.assert_called_with("Lighting: Shadow mask ON")
    
    # Toggle OFF
    _toggle_shadowmask(mock_window)
    
    assert light_manager.shadowmask_enabled is False
    mock_window.player_hud.enqueue_toast.assert_called_with("Lighting: Shadow mask OFF")

def test_toggle_triggers_rebuild(light_manager, mock_window):
    light_manager._rebuild_layer = MagicMock()
    
    light_manager.toggle_shadowmask()
    
    assert light_manager._rebuild_layer.called

def test_rebuild_uses_flag_not_env(light_manager, mock_window):
    # Ensure environment is OFF
    with patch.dict(os.environ, {"MESH_SHADOWCAST_MASK": "0"}):
        # Enable flag manually
        light_manager.shadowmask_enabled = True
        
        # Setup mocks for rebuild path
        light_manager._static_configs = [{"x": 0, "y": 0, "radius": 100, "enabled": True}]
        light_manager._get_light_polygon_points = MagicMock(return_value=[(0,0), (10,0), (10,10)])
        light_manager._is_valid_polygon = MagicMock(return_value=True)
        light_manager._add_polygon_light = MagicMock(return_value=True)
        
        # Rebuild
        light_manager._rebuild_layer()
        
        # Should use polygon path because flag is True, ignoring env var
        assert light_manager._add_polygon_light.called
        
        # Disable flag
        light_manager.shadowmask_enabled = False
        light_manager._add_polygon_light.reset_mock()
        light_manager._add_light = MagicMock()
        
        # Rebuild
        light_manager._rebuild_layer()
        
        # Should NOT use polygon path
        assert not light_manager._add_polygon_light.called
        assert light_manager._add_light.called
