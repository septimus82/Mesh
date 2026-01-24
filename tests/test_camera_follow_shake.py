from __future__ import annotations

import math
from unittest.mock import patch

import pytest

from engine.camera_controller import CameraController

pytestmark = pytest.mark.fast


class _StubWindow:
    def __init__(self) -> None:
        self.width = 320
        self.height = 180
        self.world_width = 2000
        self.world_height = 2000


class _StubCamera:
    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN001
        self.position = (0.0, 0.0)

    def move_to(self, pos, speed):  # noqa: ANN001
        self.position = pos


@patch("engine.camera_controller.ArcadeCamera", _StubCamera)
def test_camera_follow_converges_within_frames() -> None:
    window = _StubWindow()
    controller = CameraController(window)
    target = (500.0, 250.0)
    dt = 1.0 / 60.0

    for _ in range(120):
        controller.update_camera_follow(
            target_x=target[0],
            target_y=target[1],
            dt=dt,
            follow_strength=5.0,
        )

    cx, cy = controller.get_camera_center()
    assert math.hypot(cx - target[0], cy - target[1]) < 1.0


@patch("engine.camera_controller.ArcadeCamera", _StubCamera)
def test_shake_deterministic_with_seed() -> None:
    window = _StubWindow()
    controller = CameraController(window)
    controller.add_camera_trauma(1.0, decay=0.0, max_offset=10.0, frequency=12.0, seed=123)
    dt = 1.0 / 60.0
    offsets = []
    for _ in range(10):
        controller._update_camera_shake(dt)
        offsets.append((controller.shake_state.offset_x, controller.shake_state.offset_y))

    controller_b = CameraController(window)
    controller_b.add_camera_trauma(1.0, decay=0.0, max_offset=10.0, frequency=12.0, seed=123)
    offsets_b = []
    for _ in range(10):
        controller_b._update_camera_shake(dt)
        offsets_b.append((controller_b.shake_state.offset_x, controller_b.shake_state.offset_y))

    assert offsets == offsets_b


@patch("engine.camera_controller.ArcadeCamera", _StubCamera)
def test_gui_camera_unchanged_by_shake() -> None:
    window = _StubWindow()
    controller = CameraController(window)
    controller.gui_camera.position = (5.0, 6.0)
    controller.add_camera_trauma(1.0, decay=0.0, max_offset=10.0, frequency=12.0, seed=42)

    controller.update_camera_follow(target_x=100.0, target_y=0.0, dt=1.0 / 60.0)

    assert controller.gui_camera.position == (5.0, 6.0)
