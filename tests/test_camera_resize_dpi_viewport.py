"""HiDPI viewport regression tests for CameraController.resize().

Why existing tests/test_camera_resize_contract.py did not catch the bug:
headless stubs use scale=1.0 where logical window size equals framebuffer size,
so driving the GL viewport from window.rect (logical) and get_framebuffer_size()
(physical) produces identical numbers. The bug only appears when Windows DPI
scaling (e.g. 125%) makes framebuffer ~= logical * scale.
"""

from __future__ import annotations

import pytest

from engine.camera_controller import CameraController
from tests.test_camera_resize_contract import _HeadlessWindow, _visible_rect

pytestmark = pytest.mark.fast


class _HiDPIHeadlessWindow(_HeadlessWindow):
    def __init__(self, logical_width: int, logical_height: int, *, scale: float = 1.25) -> None:
        self._dpi_scale = float(scale)
        super().__init__(logical_width, logical_height)

    def set_size(self, width: int, height: int) -> None:
        from tests.test_camera_resize_contract import _Rect

        self.width = width
        self.height = height
        self.rect = _Rect(0, 0, width, height)
        fb_width = int(round(width * self._dpi_scale))
        fb_height = int(round(height * self._dpi_scale))
        self._framebuffer = (fb_width, fb_height)
        self.ctx.screen.viewport = (0, 0, fb_width, fb_height)

    @property
    def scale(self) -> float:
        return self._dpi_scale


def test_hidpi_resize_sets_viewport_to_framebuffer_not_logical() -> None:
    window = _HiDPIHeadlessWindow(2048, 1080, scale=1.25)
    controller = CameraController(window)

    window.set_size(2048, 1080)
    controller.resize(2048, 1080)

    fb_width, fb_height = window.get_framebuffer_size()
    assert (fb_width, fb_height) == (2560, 1350)
    assert window.width == 2048
    assert window.height == 1080

    assert (controller.camera.viewport_width, controller.camera.viewport_height) == (
        fb_width,
        fb_height,
    )
    assert (controller.gui_camera.viewport_width, controller.gui_camera.viewport_height) == (
        fb_width,
        fb_height,
    )
    assert (controller.camera.viewport_width, controller.camera.viewport_height) != (
        window.width,
        window.height,
    )


def test_hidpi_resize_keeps_projection_in_logical_coordinates() -> None:
    window = _HiDPIHeadlessWindow(2048, 1080, scale=1.25)
    controller = CameraController(window)

    window.set_size(2048, 1080)
    controller.resize(2048, 1080)

    assert _visible_rect(controller.gui_camera) == (0.0, 0.0, 2048.0, 1080.0)
    assert _visible_rect(controller.camera) != (0.0, 0.0, 2560.0, 1350.0)


def test_hidpi_sync_gui_camera_compares_against_framebuffer() -> None:
    window = _HiDPIHeadlessWindow(1280, 720, scale=1.25)
    controller = CameraController(window)
    controller.resize(1280, 720)

    window.set_size(1600, 900)
    fb_width, fb_height = window.get_framebuffer_size()

    controller.sync_gui_camera_to_window()

    assert (controller.gui_camera.viewport_width, controller.gui_camera.viewport_height) == (
        fb_width,
        fb_height,
    )
    assert _visible_rect(controller.gui_camera) == (0.0, 0.0, 1600.0, 900.0)


def test_scale_one_headless_still_matches_logical_viewport() -> None:
    """At scale=1.0 the framebuffer and logical sizes coincide (CI environment)."""
    window = _HeadlessWindow(1600, 900)
    controller = CameraController(window)
    controller.resize(1600, 900)

    assert (controller.gui_camera.viewport_width, controller.gui_camera.viewport_height) == (
        1600,
        900,
    )
    assert _visible_rect(controller.gui_camera) == (0.0, 0.0, 1600.0, 900.0)
