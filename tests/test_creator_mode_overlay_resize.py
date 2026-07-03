from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.camera_controller import CameraController
from engine.editor.creator_mode import CreatorModeController
from engine.editor.creator_mode.creator_overlay import build_creator_overlay_model
from engine.editor.creator_mode.creator_overlay_renderer import build_creator_overlay_draw_commands
from tests.test_camera_resize_contract import _HeadlessWindow, _visible_rect

pytestmark = pytest.mark.fast


def test_sync_gui_camera_to_window_after_window_set_size_without_resize() -> None:
    window = _HeadlessWindow(1280, 720)
    controller = CameraController(window)
    assert _visible_rect(controller.gui_camera) == (0.0, 0.0, 1280.0, 720.0)

    window.set_size(1600, 900)
    assert _visible_rect(controller.gui_camera) == (0.0, 0.0, 1280.0, 720.0)

    controller.sync_gui_camera_to_window()
    assert _visible_rect(controller.gui_camera) == (0.0, 0.0, 1600.0, 900.0)


def test_use_gui_camera_syncs_before_activation(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _HeadlessWindow(1280, 720)
    controller = CameraController(window)
    window.set_size(1920, 1080)
    used: list[bool] = []
    monkeypatch.setattr(controller.gui_camera, "use", lambda: used.append(True))

    controller.use_gui_camera()

    assert used == [True]
    assert _visible_rect(controller.gui_camera) == (0.0, 0.0, 1920.0, 1080.0)


def test_creator_overlay_geometry_tracks_resize_dimensions() -> None:
    controller = CreatorModeController(SimpleNamespace(selected_entity=None))
    controller.show()
    model = build_creator_overlay_model(controller.build_snapshot())

    small = build_creator_overlay_draw_commands(model, 800, 600)
    large = build_creator_overlay_draw_commands(model, 1600, 900)

    small_top = next(command for command in small if command.region == "top" and command.kind == "rect")
    large_top = next(command for command in large if command.region == "top" and command.kind == "rect")

    assert small_top.width == pytest.approx(800.0)
    assert large_top.width == pytest.approx(1600.0)
    assert large_top.y != small_top.y
    assert large_top.x != small_top.x


def test_creator_overlay_bottom_panel_tracks_resize_dimensions() -> None:
    controller = CreatorModeController(SimpleNamespace(selected_entity=None))
    controller.show()
    model = build_creator_overlay_model(controller.build_snapshot())

    small = build_creator_overlay_draw_commands(model, 800, 600)
    large = build_creator_overlay_draw_commands(model, 1600, 900)

    small_bottom = next(command for command in small if command.region == "bottom" and command.kind == "rect")
    large_bottom = next(command for command in large if command.region == "bottom" and command.kind == "rect")

    assert small_bottom.width == pytest.approx(800.0)
    assert large_bottom.width == pytest.approx(1600.0)
    assert large_bottom.height != small_bottom.height
