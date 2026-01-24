import pytest
from unittest.mock import MagicMock, patch
from engine.game_state_controller import GameStateController
from engine.config import EngineConfig
from engine.camera_controller import CameraController, CameraArea

class MockWindow:
    def __init__(self):
        cfg = EngineConfig()
        self.width = cfg.width
        self.height = cfg.height
        self.world_width = 2000
        self.world_height = 2000

def test_game_state_flags():
    window = MockWindow()
    controller = GameStateController(window)
    
    assert controller.get_flag("test_flag") is False
    controller.set_flag("test_flag", True)
    assert controller.get_flag("test_flag") is True
    controller.set_flag("test_flag", False)
    assert controller.get_flag("test_flag") is False

def test_game_state_counters():
    window = MockWindow()
    controller = GameStateController(window)
    
    assert controller.get_counter("coins") == 0.0
    controller.inc_counter("coins", 10)
    assert controller.get_counter("coins") == 10.0
    controller.inc_counter("coins", 5.5)
    assert controller.get_counter("coins") == 15.5

def test_game_state_spawn_point():
    window = MockWindow()
    controller = GameStateController(window)
    
    assert controller.get_next_spawn_point() is None
    controller.set_next_spawn_point("spawn_1")
    assert controller.get_next_spawn_point() == "spawn_1"
    
    consumed = controller.consume_next_spawn_point()
    assert consumed == "spawn_1"
    assert controller.get_next_spawn_point() is None

@patch("engine.camera_controller.ArcadeCamera")
def test_camera_shake(MockCamera):
    window = MockWindow()
    controller = CameraController(window)
    
    controller.start_camera_shake(duration=1.0, amplitude=10.0)
    assert controller.shake_state.duration == 1.0
    assert controller.shake_state.amplitude == 10.0
    
    controller.stop_camera_shake()
    assert controller.shake_state.duration == 0.0
    assert controller.shake_state.amplitude == 0.0

@patch("engine.camera_controller.ArcadeCamera")
def test_camera_zoom(MockCamera):
    window = MockWindow()
    controller = CameraController(window)
    
    controller.set_zoom_target(2.0)
    assert controller.zoom_state.target == 2.0
    
    # Simulate update
    controller._update_camera_zoom(0.1)
    assert controller.zoom_state.current > 1.0

@patch("engine.camera_controller.ArcadeCamera")
def test_camera_clamp_rect(MockCamera):
    window = MockWindow()
    controller = CameraController(window)

    # Rect: 0,0 to 1000,1000
    rect = (0.0, 0.0, 1000.0, 1000.0)
    half_w = window.width / 2.0
    half_h = window.height / 2.0
    min_x = rect[0] + half_w
    max_x = rect[2] - half_w
    min_y = rect[1] + half_h
    max_y = rect[3] - half_h
    # If the window is larger than the rect, clamp to rect center
    center_x = (rect[0] + rect[2]) / 2.0
    center_y = (rect[1] + rect[3]) / 2.0

    # Test inside
    x, y = controller.clamp_camera_to_rect(500, 500, rect)
    assert x == 500
    assert y == 500

    # Test left bound
    x, y = controller.clamp_camera_to_rect(0, 500, rect)
    expected_left = center_x if min_x > max_x else min_x
    assert x == expected_left  # Min x

    # Test right bound
    x, y = controller.clamp_camera_to_rect(1000, 500, rect)
    expected_right = center_x if min_x > max_x else max_x
    assert x == expected_right  # Max x
