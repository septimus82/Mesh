from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import engine.editor_controller as editor_module
from engine.editor_controller import EditorModeController
from tests._editor_window_stub import EditorWindowStub, as_game_window


class _StubSceneController:
    def __init__(self, sprites: list) -> None:
        self.tilemap_instance = None
        self._sprites = sprites

    def _ensure_entity_data_dict(self, sprite):
        if not isinstance(getattr(sprite, "mesh_entity_data", None), dict):
            sprite.mesh_entity_data = {}
        return sprite.mesh_entity_data

    def _apply_collision_poly(self, *_args, **_kwargs):
        return None

    def build_scene_snapshot(self):
        return {}

    @property
    def all_sprites(self):
        return list(self._sprites)


class _StubSprite:
    def __init__(self, data: dict) -> None:
        self.mesh_entity_data = data
        self.mesh_name = data.get("name", "entity")


class _StubPrefabs:
    def __init__(self, prefab_entity: dict) -> None:
        self.prefab_entity = prefab_entity

    def get_prefab(self, prefab_id: str):
        if prefab_id != "p_wall":
            return None
        return {"id": prefab_id, "entity": self.prefab_entity}


def _build_controller(monkeypatch, prefab_entity: dict) -> EditorModeController:
    monkeypatch.setattr(editor_module, "PREFAB_PALETTE", [])
    monkeypatch.setattr(editor_module, "load_prefab_palette", lambda *a, **k: [])
    monkeypatch.setattr("engine.prefabs.get_prefab_manager", lambda: _StubPrefabs(prefab_entity))

    window = EditorWindowStub(scene_controller=_StubSceneController([]))
    controller = EditorModeController(as_game_window(window))
    controller.active = True
    return controller


def test_apply_prefab_shapes_missing_only(monkeypatch) -> None:
    prefab_entity = {
        "collision_poly": [[0, 0], [8, 0], [0, 8]],
        "occluder_poly": [[-4, -4], [4, -4], [4, 4], [-4, 4]],
    }
    controller = _build_controller(monkeypatch, prefab_entity)
    sprite = _StubSprite(
        {
            "name": "shape_entity",
            "prefab_id": "p_wall",
            "collision_poly": [[1, 1], [2, 1], [1, 2]],
        }
    )
    controller.window.scene_controller._sprites.append(sprite)
    controller.selected_entity = sprite

    ok = controller._apply_prefab_shapes(only_missing=True)
    assert ok is True
    data = sprite.mesh_entity_data
    assert data["collision_poly"] == [[1.0, 1.0], [2.0, 1.0], [1.0, 2.0]]
    assert data["occluder_poly"] == [[-4.0, -4.0], [4.0, -4.0], [4.0, 4.0], [-4.0, 4.0]]
    assert controller.undo_stack
    assert controller.undo_stack[-1]["type"] == "EditShapes"


def test_reset_prefab_shapes_overwrites(monkeypatch) -> None:
    prefab_entity = {
        "collision_poly": [[0, 0], [8, 0], [0, 8]],
    }
    controller = _build_controller(monkeypatch, prefab_entity)
    sprite = _StubSprite(
        {
            "name": "shape_entity",
            "prefab_id": "p_wall",
            "collision_poly": [[1, 1], [2, 1], [1, 2]],
            "occluder_poly": [[-1, -1], [1, -1], [1, 1], [-1, 1]],
        }
    )
    controller.window.scene_controller._sprites.append(sprite)
    controller.selected_entity = sprite

    ok = controller._apply_prefab_shapes(only_missing=False)
    assert ok is True
    data = sprite.mesh_entity_data
    assert data["collision_poly"] == [[0.0, 0.0], [8.0, 0.0], [0.0, 8.0]]
    assert "occluder_poly" not in data
    assert controller.undo_stack
    assert controller.undo_stack[-1]["type"] == "EditShapes"


def test_edit_shapes_undo_redo_missing_entity_no_crash(monkeypatch) -> None:
    prefab_entity = {
        "collision_poly": [[0, 0], [8, 0], [0, 8]],
    }
    controller = _build_controller(monkeypatch, prefab_entity)
    sprite = _StubSprite({"name": "shape_entity", "prefab_id": "p_wall"})
    controller.window.scene_controller._sprites.append(sprite)
    controller.selected_entity = sprite

    assert controller._apply_prefab_shapes(only_missing=False) is True
    controller.window.scene_controller._sprites.clear()
    controller.undo_last()
    controller.redo_last()
