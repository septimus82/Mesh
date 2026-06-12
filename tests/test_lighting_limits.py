from unittest.mock import patch

import arcade

from engine.lighting import LightManager


class DummyWindow:
    def __init__(self):
        self.width = 100
        self.height = 100


class DummySprite:
    def __init__(self, x: float, y: float):
        self.center_x = x
        self.center_y = y


@patch("engine.lighting._LightLayer")
@patch("engine.lighting._Light")
def test_static_light_cap(mock_light, mock_layer):
    window = DummyWindow()
    mgr = LightManager(window, max_static_lights=1, enabled=True)
    # Ensure available is True (mocks make it so, but let's be sure)
    assert mgr.available

    mgr.configure_scene_lights(
        [
            {"x": 0, "y": 0, "radius": 10, "color": arcade.color.WHITE},
            {"x": 10, "y": 10, "radius": 10, "color": arcade.color.WHITE},
        ]
    )
    stats = mgr.get_stats()
    assert stats["static_count"] == 1


@patch("engine.lighting._LightLayer")
@patch("engine.lighting._Light")
def test_dynamic_light_cap(mock_light, mock_layer):
    window = DummyWindow()
    mgr = LightManager(window, max_dynamic_lights=1, enabled=True)
    assert mgr.available

    s1 = DummySprite(0, 0)
    s2 = DummySprite(10, 10)
    h1 = mgr.register_dynamic_light(owner=s1, radius=10, color=arcade.color.WHITE)
    h2 = mgr.register_dynamic_light(owner=s2, radius=10, color=arcade.color.WHITE)
    assert h1 is not None
    assert h2 is None
    stats = mgr.get_stats()
    assert stats["dynamic_count"] == 1
