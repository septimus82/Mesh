from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import arcade
import engine.editor_controller as editor_module
from engine.editor_controller import EditorModeController


class _StubSprite:
    def __init__(self, *, x: float, y: float, points: list[list[float]]) -> None:
        self.center_x = x
        self.center_y = y
        self.mesh_name = "shape_entity"
        self.mesh_tag = "entity"
        self.mesh_entity_data = {"name": "shape_entity", "x": x, "y": y, "occluder_poly": points}


def _build_controller(monkeypatch) -> EditorModeController:
    monkeypatch.setattr(editor_module, "PREFAB_PALETTE", [])
    monkeypatch.setattr(editor_module, "load_prefab_palette", lambda *a, **k: [])

    window = SimpleNamespace()
    window.strict_mode = False
    window.paused = False
    window.width = 800
    window.height = 600
    window._mouse_x = 0
    window._mouse_y = 0
    window.scene_controller = MagicMock()
    window.screen_to_world = lambda x, y: (float(x), float(y))
    window.camera_controller = SimpleNamespace(zoom=1.0)

    controller = EditorModeController(window)  # type: ignore[arg-type]
    controller.active = True
    return controller


def test_shape_drag_updates_vertex_without_adding(monkeypatch) -> None:
    controller = _build_controller(monkeypatch)
    sprite = _StubSprite(x=100.0, y=100.0, points=[[0, 0], [10, 0], [0, 10]])
    controller.selected_entity = sprite
    assert controller.toggle_shape_edit_mode("occluder") is True

    before_len = len(controller.shape_edit_points)
    controller.handle_mouse_click(100, 100, arcade.MOUSE_BUTTON_LEFT, 0)
    assert controller.shape_drag_index == 0

    controller.handle_mouse_drag(110, 120, 10, 20, arcade.MOUSE_BUTTON_LEFT, 0)
    assert len(controller.shape_edit_points) == before_len
    assert controller.shape_edit_points[0] == (10.0, 20.0)


def test_shape_snap_rounds_dragged_point(monkeypatch) -> None:
    controller = _build_controller(monkeypatch)
    controller.grid_size = 10
    sprite = _StubSprite(x=100.0, y=100.0, points=[[0, 0], [10, 0], [0, 10]])
    controller.selected_entity = sprite
    assert controller.toggle_shape_edit_mode("occluder") is True

    controller.handle_input(arcade.key.G, 0)
    assert controller.shape_snap_enabled is True

    controller.handle_mouse_click(100, 100, arcade.MOUSE_BUTTON_LEFT, 0)
    controller.handle_mouse_drag(112, 117, 12, 17, arcade.MOUSE_BUTTON_LEFT, 0)
    assert controller.shape_edit_points[0] == (10.0, 20.0)


def test_shape_click_far_adds_point(monkeypatch) -> None:
    controller = _build_controller(monkeypatch)
    sprite = _StubSprite(x=100.0, y=100.0, points=[[0, 0], [10, 0], [0, 10]])
    controller.selected_entity = sprite
    assert controller.toggle_shape_edit_mode("occluder") is True

    before_len = len(controller.shape_edit_points)
    controller.handle_mouse_click(200, 200, arcade.MOUSE_BUTTON_LEFT, 0)
    assert len(controller.shape_edit_points) == before_len + 1
    assert controller.shape_edit_points[-1] == (100.0, 100.0)
