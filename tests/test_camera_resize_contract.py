from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.camera_controller import CameraController

pytestmark = pytest.mark.fast


class _Rect:
    def __init__(self, x: float, y: float, width: float, height: float) -> None:
        self.x = x
        self.y = y
        self.width = width
        self.height = height


class _HeadlessWindow:
    def __init__(self, width: int = 1280, height: int = 720) -> None:
        self.ctx = SimpleNamespace(screen=SimpleNamespace(viewport=(0, 0, width, height)))
        self.world_width = None
        self.world_height = None
        self._framebuffer = (width, height)
        self.set_size(width, height)

    def set_size(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.rect = _Rect(0, 0, width, height)
        self._framebuffer = (width, height)
        self.ctx.screen.viewport = (0, 0, width, height)

    def get_framebuffer_size(self) -> tuple[int, int]:
        return self._framebuffer


def _visible_rect(camera) -> tuple[float, float, float, float]:  # noqa: ANN001
    projection = camera.projection
    return (
        camera.position[0] + projection.left,
        camera.position[1] + projection.bottom,
        camera.position[0] + projection.right,
        camera.position[1] + projection.top,
    )


def test_world_viewport_tracks_resize() -> None:
    window = _HeadlessWindow()
    controller = CameraController(window)
    assert (controller.camera.viewport_width, controller.camera.viewport_height) == (1280, 720)

    window.set_size(1600, 900)
    controller.resize(1600, 900)

    assert (controller.camera.viewport_width, controller.camera.viewport_height) == (1600, 900)


def test_world_zoom_survives_resize() -> None:
    window = _HeadlessWindow()
    controller = CameraController(window)
    controller.camera.zoom = 2.0

    window.set_size(1600, 900)
    controller.resize(1600, 900)

    assert controller.camera.zoom == 2.0


def test_world_position_survives_resize() -> None:
    window = _HeadlessWindow()
    controller = CameraController(window)
    controller.camera.position = (123.0, 456.0)

    window.set_size(1600, 900)
    controller.resize(1600, 900)

    assert tuple(controller.camera.position) == (123.0, 456.0)


def test_gui_visible_rect_tracks_resize() -> None:
    window = _HeadlessWindow()
    controller = CameraController(window)

    window.set_size(1600, 900)
    controller.resize(1600, 900)

    assert _visible_rect(controller.gui_camera) == (0.0, 0.0, 1600.0, 900.0)


def test_resize_tolerates_cameras_without_match_window() -> None:
    controller = CameraController.__new__(CameraController)
    controller.camera = SimpleNamespace()
    controller.gui_camera = SimpleNamespace()

    controller.resize(1600, 900)


def test_sync_gui_camera_to_window_is_noop_when_already_matched() -> None:
    window = _HeadlessWindow(1280, 720)
    controller = CameraController(window)
    controller.resize(1280, 720)

    controller.sync_gui_camera_to_window()

    assert _visible_rect(controller.gui_camera) == (0.0, 0.0, 1280.0, 720.0)
