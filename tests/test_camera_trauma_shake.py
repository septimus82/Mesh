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
def test_trauma_shake_is_deterministic_and_decays() -> None:
    window = _StubWindow()
    controller = CameraController(window)
    controller.add_camera_trauma(1.0, decay=1.0, max_offset=10.0, frequency=12.0, seed=123)

    dt = 1.0 / 60.0
    offsets = []
    for _ in range(5):
        controller._update_camera_shake(dt)
        offsets.append((controller.shake_state.offset_x, controller.shake_state.offset_y))

    controller_b = CameraController(window)
    controller_b.add_camera_trauma(1.0, decay=1.0, max_offset=10.0, frequency=12.0, seed=123)
    offsets_b = []
    for _ in range(5):
        controller_b._update_camera_shake(dt)
        offsets_b.append((controller_b.shake_state.offset_x, controller_b.shake_state.offset_y))

    assert offsets == offsets_b

    controller._update_camera_shake(1.0)
    assert controller.shake_state.trauma == pytest.approx(0.0)
