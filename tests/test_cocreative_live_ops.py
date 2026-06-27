from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from typing import Any

from engine.editor_controller import EditorModeController
from engine.scene_runtime.persistence import build_scene_snapshot


class _FakeSprite:
    def __init__(self, entity: dict[str, Any]) -> None:
        self.mesh_entity_data = entity
        self.mesh_name = str(entity.get("name") or "")
        self.center_x = float(entity.get("x", 0.0))
        self.center_y = float(entity.get("y", 0.0))
        self.scale = float(entity.get("scale", 1.0))
        self.angle = float(entity.get("rotation", 0.0))
        self.mesh_behaviour_configs: list[dict[str, Any]] = []


class _FakeSceneController:
    def __init__(self, window: Any) -> None:
        self.window = window
        self.current_scene_path = "scenes/live.json"
        self._loaded_scene_data: dict[str, Any] = {"settings": {}, "entities": []}
        self.layers: dict[str, list[_FakeSprite]] = {"entities": []}
        self.solid_sprites: list[_FakeSprite] = []
        self.tilemap_instance = None

    @property
    def all_sprites(self) -> list[_FakeSprite]:
        sprites: list[_FakeSprite] = []
        for layer in self.layers.values():
            sprites.extend(layer)
        return sprites

    def _create_sprite(self, entity: dict[str, Any]) -> _FakeSprite:
        return _FakeSprite(entity)

    def add_sprite_to_layer(self, sprite: _FakeSprite, layer_name: str = "entities") -> None:
        self.layers.setdefault(layer_name, []).append(sprite)

    def build_scene_snapshot(self, compact: bool = False) -> dict[str, Any]:
        return build_scene_snapshot(self, compact=compact)


class _FakeWindow:
    def __init__(self) -> None:
        self.scene_controller = _FakeSceneController(self)
        self.strict_mode = False
        self.width = 800
        self.height = 600
        self.paused = False
        self.camera_controller = SimpleNamespace(
            zoom_state=SimpleNamespace(
                current=1.0,
                target=1.0,
                speed=1.0,
                min_zoom=0.5,
                max_zoom=2.0,
            )
        )
        self.game_state = SimpleNamespace(snapshot=lambda: {})
        self.scene_loader = SimpleNamespace(apply_scene_defaults=lambda snapshot: snapshot)
        self.screen_to_world = lambda x, y: (x, y)


def _make_controller() -> EditorModeController:
    controller = EditorModeController(_FakeWindow())
    controller.prefab_palette = [
        {
            "id": "crate",
            "display_name": "Crate",
            "entity": {"name": "crate", "sprite": "assets/crate.png", "layer": "entities"},
        }
    ]
    controller.active = True
    controller._refresh_hierarchy_list = lambda: None  # type: ignore[method-assign]
    controller._refresh_inspector_items = lambda: None  # type: ignore[method-assign]
    controller._refresh_entity_panels_list = lambda *, sync_selected=False: None  # type: ignore[method-assign]
    return controller


def _entity_names(snapshot: dict[str, Any]) -> list[str]:
    return [str(entity.get("name")) for entity in snapshot.get("entities", []) if isinstance(entity, dict)]


def test_live_add_entity_from_prefab_applies_to_scene_and_pushes_one_undo() -> None:
    controller = _make_controller()
    scene_controller = controller.window.scene_controller

    before_sprite_count = len(scene_controller.all_sprites)
    before_entity_count = len(scene_controller._loaded_scene_data["entities"])

    result = controller.apply_live_op({"type": "add_entity_from_prefab", "prefab_id": "crate", "x": 32, "y": 48})

    assert result["ok"] is True
    assert len(scene_controller.all_sprites) == before_sprite_count + 1
    assert len(scene_controller._loaded_scene_data["entities"]) == before_entity_count + 1
    assert controller.scene_dirty is True
    assert len(controller.undo.undo_stack) == 1
    assert controller.undo.undo_stack[0]["type"] == "AddEntity"
    assert not controller.undo.redo_stack


def test_live_add_entity_from_prefab_is_visible_in_snapshot_before_save() -> None:
    controller = _make_controller()

    result = controller.apply_live_op(
        {"type": "add_entity_from_prefab", "prefab_id": "crate", "x": 64, "y": 80, "name": "ai_crate"}
    )

    assert result["ok"] is True
    snapshot = controller.window.scene_controller.build_scene_snapshot(compact=False)
    assert "ai_crate" in _entity_names(snapshot)


def test_live_add_entity_from_prefab_undo_redo_updates_sprite_payload_and_snapshot() -> None:
    controller = _make_controller()
    scene_controller = controller.window.scene_controller

    result = controller.apply_live_op(
        {"type": "add_entity_from_prefab", "prefab_id": "crate", "x": 64, "y": 80, "name": "ai_crate"}
    )
    assert result["ok"] is True

    assert controller.undo.undo() is True
    assert len(scene_controller.all_sprites) == 0
    assert scene_controller._loaded_scene_data["entities"] == []
    assert "ai_crate" not in _entity_names(scene_controller.build_scene_snapshot(compact=False))

    assert controller.undo.redo() is True
    assert len(scene_controller.all_sprites) == 1
    assert [entity.get("name") for entity in scene_controller._loaded_scene_data["entities"]] == ["ai_crate"]
    assert "ai_crate" in _entity_names(scene_controller.build_scene_snapshot(compact=False))


def test_live_add_entity_from_prefab_rejects_different_scene_without_mutation() -> None:
    controller = _make_controller()
    scene_controller = controller.window.scene_controller
    before_scene = deepcopy(scene_controller._loaded_scene_data)

    result = controller.apply_live_op(
        {
            "type": "add_entity_from_prefab",
            "scene_path": "scenes/other.json",
            "prefab_id": "crate",
            "x": 32,
            "y": 48,
        }
    )

    assert result["ok"] is False
    assert len(scene_controller.all_sprites) == 0
    assert scene_controller._loaded_scene_data == before_scene
    assert controller.scene_dirty is False
    assert controller.undo.undo_stack == []
