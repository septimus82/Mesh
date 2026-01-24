from __future__ import annotations

import types
from typing import Any

import arcade

import engine.editor_controller as editor_module
from engine.editor_controller import EditorModeController


class _StubSprite:
    def __init__(self, *, name: str, x: float, y: float) -> None:
        self.mesh_name = name
        self.mesh_tag = "entity"
        self.mesh_behaviours = []
        self.mesh_behaviours_runtime = []
        self.mesh_entity_data: dict[str, Any] = {"name": name, "x": x, "y": y, "behaviour_config": {}}
        self.center_x = x
        self.center_y = y
        self.width = 32
        self.height = 32

    def collides_with_point(self, _pt) -> bool:
        return True


class _StubSceneController:
    def __init__(self, sprites: list[_StubSprite]) -> None:
        self._sprites = sprites
        self.tilemap_instance = None
        self.current_scene_path = "scenes/test_scene.json"
        self.layers = {"entities": sprites}
        self.solid_sprites: list[_StubSprite] = []

    @property
    def all_sprites(self):
        for spr in self._sprites:
            yield spr

    def _ensure_entity_data_dict(self, sprite: _StubSprite) -> dict[str, Any]:
        if not isinstance(getattr(sprite, "mesh_entity_data", None), dict):
            sprite.mesh_entity_data = {}
        return sprite.mesh_entity_data

    def _ensure_behaviour_config_root(self, entity_data: dict[str, Any]) -> dict[str, Any]:
        root = entity_data.get("behaviour_config")
        if not isinstance(root, dict):
            root = {}
            entity_data["behaviour_config"] = root
        return root

    def _apply_entity_mutation(self, sprite: _StubSprite, *, x: float | None = None, y: float | None = None, **_k) -> None:
        if x is not None:
            sprite.center_x = float(x)
            sprite.mesh_entity_data["x"] = float(x)
        if y is not None:
            sprite.center_y = float(y)
            sprite.mesh_entity_data["y"] = float(y)

    def build_scene_snapshot(self) -> dict[str, Any]:
        return {}


def test_selection_picks_topmost_and_arrow_nudges_and_pushes_undo(monkeypatch) -> None:
    monkeypatch.setattr(editor_module, "PREFAB_PALETTE", [])
    monkeypatch.setattr(editor_module, "load_prefab_palette", lambda *a, **k: [])

    s1 = _StubSprite(name="a", x=0.0, y=0.0)
    s2 = _StubSprite(name="b", x=10.0, y=20.0)
    scene = _StubSceneController([s1, s2])

    window = types.SimpleNamespace()
    window.strict_mode = False
    window.paused = False
    window.width = 800
    window.height = 600
    window._mouse_x = 0
    window._mouse_y = 0
    window.scene_controller = scene
    window.screen_to_world = lambda x, y: (float(x), float(y))

    controller = EditorModeController(window)  # type: ignore[arg-type]
    controller.toggle()
    assert controller.active is True
    assert window.paused is True

    ok = controller.handle_mouse_click(5, 5, arcade.MOUSE_BUTTON_LEFT, 0)
    assert ok is True
    assert controller.selected_entity is s2
    assert controller.entity_dragging is True
    assert controller.entity_drag_start_pos == (10.0, 20.0)

    controller.entity_dragging = False
    controller.entity_drag_start_pos = None

    before_x = s2.center_x
    consumed = controller.handle_input(arcade.key.LEFT, 0)
    assert consumed is True
    assert s2.center_x == before_x - controller.grid_size
    assert controller.undo_stack
    assert controller.undo_stack[-1]["type"] == "MoveEntity"

