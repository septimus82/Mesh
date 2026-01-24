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
def test_gui_camera_position_not_affected_by_shake() -> None:
    window = _StubWindow()
    controller = CameraController(window)
    controller.gui_camera.position = (5.0, 6.0)

    controller.add_camera_trauma(1.0, decay=0.0, max_offset=10.0, frequency=12.0, seed=42)
    controller.update_camera_follow(target_x=100.0, target_y=0.0, dt=1.0 / 60.0)

    assert controller.gui_camera.position == (5.0, 6.0)
