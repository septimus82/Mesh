import pytest
from unittest.mock import MagicMock
import os
import math
from engine.lighting import LightManager

# Mock Window
class MockWindow:
    def __init__(self):
        self.width = 800
        self.height = 600
        # We initialize LightManager, but we'll patch its internals
        self.lighting = LightManager(self, enabled=True)

def test_shadowcast_snapshot(mock_arcade_lighting, monkeypatch):
    # Enable debug flag
    monkeypatch.setenv("MESH_SHADOWCAST_DEBUG", "1")
    
    window = MockWindow()
    window.lighting.available = True
    window.lighting._layer = MagicMock()
    
    # Configure light at origin
    lights = [{"x": 0, "y": 0, "radius": 100, "color": [255, 255, 255]}]
    window.lighting.configure_scene_lights(lights)
    
    # Configure occluder: vertical wall at x=50
    # Rect: x=50, y=-50, w=10, h=100
    # Points: (50, -50), (60, -50), (60, 50), (50, 50)
    occluders = [{"id": "wall1", "type": "rect", "x": 50, "y": -50, "width": 10, "height": 100}]
    window.lighting.configure_scene_occluders(occluders)
    
    snapshot = window.lighting.get_lighting_snapshot()
    
    assert "shadowcast" in snapshot
    shadowcast = snapshot["shadowcast"]
    assert "light_0" in shadowcast
    rays = shadowcast["light_0"]
    assert len(rays) == 16
    
    # Check ray at angle 0 (index 0)
    # Should hit wall at (50, 0)
    ray0 = rays[0]
    assert ray0["angle"] == 0.0
    assert ray0["hit_occluder"] == "wall1"
    # Allow small float diffs if needed, but we rounded to 3 decimals
    assert ray0["hit"] == [50.0, 0.0]
    
    # Check ray at angle PI (index 8) -> 180 degrees
    # Should miss wall and hit max radius (-100, 0)
    ray8 = rays[8]
    assert ray8["angle"] == round(math.pi, 3)
    assert ray8["hit_occluder"] is None
    # Note: cos(pi) is -1, sin(pi) is approx 0
    # hit point should be (-100, 0)
    assert ray8["hit"] == [-100.0, 0.0]

def test_shadowcast_snapshot_disabled_by_default(mock_arcade_lighting, monkeypatch):
    # Ensure flag is unset
    monkeypatch.delenv("MESH_SHADOWCAST_DEBUG", raising=False)
    
    window = MockWindow()
    window.lighting.available = True
    window.lighting._layer = MagicMock()
    
    window.lighting.configure_scene_lights([{"x": 0, "y": 0}])
    
    snapshot = window.lighting.get_lighting_snapshot()
    assert "shadowcast" not in snapshot
