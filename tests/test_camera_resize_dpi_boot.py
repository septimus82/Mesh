"""Boot-time HiDPI camera initialization (ENGINE-RESIZE-DPI-FIX2).

#301 only ran the HiDPI viewport fix inside resize()/sync paths. At boot the
Project Browser could render before any resize event, and Camera2D's default
center-origin projection was preserved by update_values() instead of resetting
to bottom-left logical coordinates for GUI overlays.
"""

from __future__ import annotations

import pytest

from engine.camera_controller import CameraController
from tests.test_camera_resize_contract import _HeadlessWindow, _visible_rect
from tests.test_camera_resize_dpi_viewport import _HiDPIHeadlessWindow

pytestmark = pytest.mark.fast


def test_initialize_window_cameras_sets_framebuffer_viewport_at_boot() -> None:
    # ctx.screen.viewport is logical at boot (matches live Windows/arcade init).
    window = _HeadlessWindow(2048, 1080)
    window.get_framebuffer_size = lambda: (2560, 1350)  # type: ignore[method-assign]
    window.scale = 1.25
    controller = CameraController(window)
    assert (controller.gui_camera.viewport_width, controller.gui_camera.viewport_height) == (
        2048,
        1080,
    )

    controller.initialize_window_cameras()

    assert (controller.gui_camera.viewport_width, controller.gui_camera.viewport_height) == (
        2560,
        1350,
    )
    assert (controller.camera.viewport_width, controller.camera.viewport_height) == (
        2560,
        1350,
    )


def test_gui_camera_uses_bottom_left_projection_after_hidpi_match() -> None:
    window = _HiDPIHeadlessWindow(2048, 1080, scale=1.25)
    controller = CameraController(window)
    controller.initialize_window_cameras()

    assert controller.gui_camera.projection.left == pytest.approx(0.0)
    assert controller.gui_camera.projection.bottom == pytest.approx(0.0)
    assert controller.gui_camera.projection.right == pytest.approx(2048.0)
    assert controller.gui_camera.projection.top == pytest.approx(1080.0)
    assert float(controller.gui_camera.position[0]) == pytest.approx(0.0)
    assert float(controller.gui_camera.position[1]) == pytest.approx(0.0)
    assert _visible_rect(controller.gui_camera) == (0.0, 0.0, 2048.0, 1080.0)


def test_game_window_init_path_initializes_cameras_via_helper() -> None:
    window = _HiDPIHeadlessWindow(1600, 900, scale=1.25)
    controller = CameraController(window)
    controller.initialize_window_cameras()

    fb_width, fb_height = window.get_framebuffer_size()
    assert (controller.gui_camera.viewport_width, controller.gui_camera.viewport_height) == (
        fb_width,
        fb_height,
    )


def test_scale_one_boot_init_is_unchanged() -> None:
    window = _HeadlessWindow(1280, 720)
    controller = CameraController(window)
    controller.initialize_window_cameras()

    assert (controller.gui_camera.viewport_width, controller.gui_camera.viewport_height) == (
        1280,
        720,
    )
    assert _visible_rect(controller.gui_camera) == (0.0, 0.0, 1280.0, 720.0)
