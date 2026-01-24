import os
import pytest
from unittest.mock import MagicMock, patch
from engine.lighting import LightManager

@pytest.fixture
def shadowcast_env():
    with patch.dict(os.environ, {"MESH_SHADOWCAST_MASK": "1"}):
        yield

@pytest.fixture
def mock_layer():
    layer = MagicMock()
    layer.add_light_polygon = MagicMock()
    layer.add = MagicMock()
    layer.add_light = MagicMock()
    return layer

@pytest.fixture
def light_manager(mock_arcade_lighting, mock_layer):
    lm = LightManager(MagicMock())
    lm.enabled = True
    lm._layer = mock_layer
    lm._create_layer = MagicMock(return_value=mock_layer)
    lm._cast_ray = MagicMock(return_value={"hit": (150, 100)})
    yield lm

def test_polygon_light_creation(shadowcast_env, light_manager, mock_layer):
    # Configure a light
    light_config = {
        "x": 100, "y": 100, "radius": 50, "color": (255, 255, 255)
    }
    
    # Mock _get_light_polygon_points to return a valid polygon
    valid_points = [(100, 100), (150, 100), (150, 150), (100, 150)] # Square
    
    with patch.object(light_manager, "_get_light_polygon_points", return_value=valid_points):
        light_manager.configure_scene_lights([light_config])
        
        # Verify add_light_polygon was called
        assert mock_layer.add_light_polygon.called
        args, kwargs = mock_layer.add_light_polygon.call_args
        
        # Check points
        points = args[0]
        assert len(points) == 4
        
        # Check kwargs
        assert kwargs["x"] == 100
        assert kwargs["y"] == 100
        assert kwargs["radius"] == 50

def test_standard_light_creation_flag_off(light_manager, mock_layer):
    # Disable flag
    with patch.dict(os.environ, {"MESH_SHADOWCAST_MASK": "0"}):
        # Configure a light
        light_config = {
            "x": 100, "y": 100, "radius": 50, "color": (255, 255, 255)
        }
        light_manager.configure_scene_lights([light_config])
        
        # Verify add_light_polygon was NOT called
        assert not mock_layer.add_light_polygon.called
        
        # Verify standard add was called
        assert mock_layer.add_light.called or mock_layer.add.called
