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
    yield lm

def test_points_are_rounded_before_add(shadowcast_env, light_manager, mock_layer):
    # Setup a scene with one light
    light_config = {"x": 100.123456, "y": 200.987654, "radius": 50, "color": (255, 255, 255)}

    # Mock _get_light_polygon_points to return high precision points
    # Note: _get_light_polygon_points usually calls _cast_ray which rounds,
    # but we are mocking the whole method to simulate raw input or calculation drift.
    raw_points = [
        (100.123456, 200.987654), # Center
        (150.111111, 200.222222),
        (150.333333, 250.444444),
        (100.555555, 250.666666)
    ]

    with patch.object(light_manager, "_get_light_polygon_points", return_value=raw_points):
        light_manager.configure_scene_lights([light_config])

        # Verify add_light_polygon was called
        assert mock_layer.add_light_polygon.called
        args, _ = mock_layer.add_light_polygon.call_args
        points = args[0]

        # Check that points are rounded to 3 decimal places
        expected_points = [
            (100.123, 200.988),
            (150.111, 200.222),
            (150.333, 250.444),
            (100.556, 250.667)
        ]

        assert points == expected_points

        # Verify exact equality (no float drift)
        for p in points:
            assert str(p[0])[::-1].find('.') <= 3
            assert str(p[1])[::-1].find('.') <= 3

def test_validation_uses_rounded_points(shadowcast_env, light_manager, mock_layer):
    # Setup a scene
    light_config = {"x": 0, "y": 0, "radius": 100}

    # Create points that are distinct in high precision but identical when rounded
    # This should fail validation after rounding (degenerate polygon)
    # (0,0), (0.0001, 0.0001), (0.0002, 0.0002) -> (0,0), (0,0), (0,0)
    raw_points = [
        (0.0, 0.0),
        (0.0001, 0.0001),
        (0.0002, 0.0002)
    ]

    with patch.object(light_manager, "_get_light_polygon_points", return_value=raw_points):
        light_manager.configure_scene_lights([light_config])

        # Should NOT call add_light_polygon because rounded points are degenerate
        assert not mock_layer.add_light_polygon.called

        # Should fallback to standard light
        assert mock_layer.add_light.called or mock_layer.add.called
