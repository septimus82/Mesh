from __future__ import annotations

from unittest.mock import patch

import pytest

from engine.camera_controller import CameraController

pytestmark = pytest.mark.fast


class _StubWindow:
    def __init__(self) -> None:
        self.width = 320
        self.height = 180
        self.world_width = None
        self.world_height = None


class _StubCamera:
    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN001
        self.position = (0.0, 0.0)

    def move_to(self, pos, speed) -> None:  # noqa: ANN001
        self.position = pos


@patch("engine.camera_controller.ArcadeCamera", _StubCamera)
def test_deadzone_keeps_camera_still_inside_bounds() -> None:
    window = _StubWindow()
    controller = CameraController(window)

    controller.update_camera_follow(
        target_x=5.0,
        target_y=6.0,
        dt=1.0,
        follow_strength=1.0,
        deadzone_w=40.0,
        deadzone_h=40.0,
    )

    assert controller.get_camera_center() == (0.0, 0.0)


@patch("engine.camera_controller.ArcadeCamera", _StubCamera)
def test_deadzone_moves_camera_to_edge_when_outside() -> None:
    window = _StubWindow()
    controller = CameraController(window)

    controller.update_camera_follow(
        target_x=30.0,
        target_y=-25.0,
        dt=1.0,
        follow_strength=1.0,
        deadzone_w=40.0,
        deadzone_h=20.0,
    )

    assert controller.get_camera_center() == (10.0, -15.0)
