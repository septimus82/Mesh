from __future__ import annotations

import types
from typing import Any

import pytest

import engine.editor_controller as editor_module
from engine.editor_controller import EditorModeController


class _ParamDef:
    def __init__(self, default: Any, typ: Any) -> None:
        self.default = default
        self.type = typ


class _StubSprite:
    def __init__(self, entity_def: dict[str, Any]) -> None:
        self.mesh_name = str(entity_def.get("name") or "Entity")
        self.mesh_entity_data = dict(entity_def)
        self.center_x = float(entity_def.get("x", 0.0))
        self.center_y = float(entity_def.get("y", 0.0))
        self.mesh_behaviours = []
        self.mesh_behaviours_runtime = []


class _StubSceneController:
    def __init__(self) -> None:
        self.layers: dict[str, list[_StubSprite]] = {"entities": []}
        self.solid_sprites: list[_StubSprite] = []

    @property
    def all_sprites(self):
        for layer in self.layers.values():
            for sprite in layer:
                yield sprite

    def add_sprite_to_layer(self, sprite: _StubSprite, layer_name: str) -> None:
        self.layers.setdefault(layer_name, []).append(sprite)

    def _create_sprite(self, entity_def: dict[str, Any]) -> _StubSprite:
        return _StubSprite(entity_def)

    def _apply_entity_mutation(self, sprite: _StubSprite, *, x: float | None = None, y: float | None = None) -> None:
        if x is not None:
            sprite.center_x = float(x)
            sprite.mesh_entity_data["x"] = float(x)
        if y is not None:
            sprite.center_y = float(y)
            sprite.mesh_entity_data["y"] = float(y)

    def _ensure_entity_data_dict(self, sprite: _StubSprite) -> dict[str, Any]:
        return sprite.mesh_entity_data

    def _ensure_behaviour_config_root(self, entity_data: dict[str, Any]) -> dict[str, Any]:
        root = entity_data.get("behaviour_config")
        if not isinstance(root, dict):
            root = {}
            entity_data["behaviour_config"] = root
        return root

    def _get_behaviour_configs_for_sprite(self, _sprite: _StubSprite) -> list[dict[str, Any]]:
        return []


@pytest.mark.fast
def test_undo_redo_entity_edits(monkeypatch: pytest.MonkeyPatch) -> None:
    prefab = {"id": "crate", "display_name": "Crate", "entity": {"name": "Crate"}}
    monkeypatch.setattr(editor_module, "PREFAB_PALETTE", [prefab])
    monkeypatch.setattr(editor_module, "load_prefab_palette", lambda *a, **k: [prefab])

    def fake_param_defs(_name: str):
        return {"hp": _ParamDef(default=10, typ=int)}

    monkeypatch.setattr(editor_module, "get_behaviour_param_defs", fake_param_defs)

    window = types.SimpleNamespace()
    window.strict_mode = False
    window.scene_controller = _StubSceneController()
    window.screen_to_world = lambda x, y: (x, y)

    controller = EditorModeController(window)  # type: ignore[arg-type]
    controller.active = True
    controller.palette_active = True
    controller.palette_index = 0

    controller.place_entity_at_mouse(10, 20)
    assert len(window.scene_controller.layers["entities"]) == 1
    sprite = window.scene_controller.layers["entities"][0]
    controller.selected_entity = sprite

    controller.nudge_selected(16, 0)
    controller._update_param("health", "hp", 5)
    controller.delete_selected()
    assert len(window.scene_controller.layers["entities"]) == 0

    controller.undo_last()  # undo delete
    assert len(window.scene_controller.layers["entities"]) == 1
    sprite = window.scene_controller.layers["entities"][0]
    assert sprite.mesh_entity_data["behaviour_config"]["health"]["hp"] == 5

    controller.undo_last()  # undo param change
    assert sprite.mesh_entity_data["behaviour_config"]["health"]["hp"] == 10

    controller.undo_last()  # undo move
    assert sprite.center_x == 16.0
    assert sprite.center_y == 16.0

    controller.undo_last()  # undo add
    assert len(window.scene_controller.layers["entities"]) == 0

    controller.redo_last()  # redo add
    assert len(window.scene_controller.layers["entities"]) == 1
    sprite = window.scene_controller.layers["entities"][0]

    controller.redo_last()  # redo move
    assert sprite.center_x == 32.0

    controller.redo_last()  # redo param change
    assert sprite.mesh_entity_data["behaviour_config"]["health"]["hp"] == 5

    controller.redo_last()  # redo delete
    assert len(window.scene_controller.layers["entities"]) == 0
