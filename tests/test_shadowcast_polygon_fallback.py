import os
from unittest.mock import MagicMock, patch

import pytest

from engine.lighting import LightManager


@pytest.fixture
def shadowcast_env():
    with patch.dict(os.environ, {"MESH_SHADOWCAST_MASK": "1"}):
        yield

@pytest.fixture
def mock_layer():
    layer = MagicMock()
    # Setup standard add methods to be present
    layer.add = MagicMock()
    layer.add_light = MagicMock()
    # Setup polygon methods to be present by default (can be overridden in tests)
    layer.add_light_polygon = MagicMock()
    return layer

@pytest.fixture
def light_manager(mock_arcade_lighting, mock_layer):
    lm = LightManager(MagicMock())
    lm.enabled = True
    lm._layer = mock_layer
    lm._create_layer = MagicMock(return_value=mock_layer)
    yield lm

def test_degenerate_polygon_fallback(shadowcast_env, light_manager, mock_layer):
    # Setup a scene with one light
    light_config = {"x": 0, "y": 0, "radius": 100, "color": (255, 255, 255), "id": "test_light"}

    # Mock _get_light_polygon_points to return degenerate points (not enough points)
    with patch.object(light_manager, "_get_light_polygon_points", return_value=[(0,0), (1,1)]):
        light_manager.configure_scene_lights([light_config])

        # Should NOT call add_light_polygon
        assert not mock_layer.add_light_polygon.called

        # Should call standard add (via _add_light probing)
        # _add_light probes: add_light, add. Since add_light is present on mock, it should be called.
        assert mock_layer.add_light.called

        # Check logging counter
        counters = getattr(light_manager, "_mesh_logged_counters", {})
        assert "invalid_polygon" in counters
        assert counters["invalid_polygon"] == 1

def test_zero_area_polygon_fallback(shadowcast_env, light_manager, mock_layer):
    # Setup a scene with one light
    light_config = {"x": 0, "y": 0, "radius": 100, "color": (255, 255, 255), "id": "test_light_2"}

    # Mock _get_light_polygon_points to return collinear points (zero area)
    with patch.object(light_manager, "_get_light_polygon_points", return_value=[(0,0), (1,1), (2,2)]):
        light_manager.configure_scene_lights([light_config])

        # Should NOT call add_light_polygon
        assert not mock_layer.add_light_polygon.called

        # Should call standard add
        assert mock_layer.add_light.called

        # Check logging counter
        counters = getattr(light_manager, "_mesh_logged_counters", {})
        assert "invalid_polygon" in counters
        assert counters["invalid_polygon"] == 1

def test_missing_polygon_method_fallback(shadowcast_env, light_manager, mock_layer):
    # Setup a scene with one light
    light_config = {"x": 0, "y": 0, "radius": 100, "color": (255, 255, 255), "id": "test_light_3"}

    # Simulate missing methods by setting them to None (callable(None) is False)
    mock_layer.add_light_polygon = None
    mock_layer.add_polygon_light = None
    mock_layer.add_hole_polygon = None

    # Ensure standard add methods exist
    mock_layer.add = MagicMock()

    # Mock _get_light_polygon_points to return VALID points
    valid_points = [(0,0), (10,0), (10,10), (0,10)]
    with patch.object(light_manager, "_get_light_polygon_points", return_value=valid_points):
        light_manager.configure_scene_lights([light_config])

        # Should try to add polygon light but fail (return False)
        # Should call standard add
        assert mock_layer.add_light.called
