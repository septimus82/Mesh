from __future__ import annotations

from types import SimpleNamespace

import engine.editor_controller as editor_module
from engine.editor_controller import EditorModeController
from engine.editor_prefab_variant_ops import DiffRow
from tests._typing import as_any


class _StubSprite(SimpleNamespace):
    def __init__(self, entity_data: dict) -> None:
        super().__init__(
            mesh_entity_data=entity_data,
            mesh_name=entity_data.get("mesh_name") or entity_data.get("name") or entity_data.get("id") or "",
            center_x=float(entity_data.get("x", 0.0) or 0.0),
            center_y=float(entity_data.get("y", 0.0) or 0.0),
            angle=float(entity_data.get("rotation", 0.0) or 0.0),
            scale=float(entity_data.get("scale", 1.0) or 1.0),
        )


class _StubSceneController:
    def __init__(self, payload: dict, sprites: list[_StubSprite]) -> None:
        self._loaded_scene_data = payload
        self.all_sprites = sprites

    def _ensure_entity_data_dict(self, sprite: _StubSprite) -> dict:
        return sprite.mesh_entity_data

    def _apply_entity_mutation(
        self,
        sprite: _StubSprite,
        *,
        x: float | None = None,
        y: float | None = None,
        scale: float | None = None,
        tag: str | None = None,
    ) -> None:
        if x is not None:
            sprite.center_x = float(x)
            sprite.mesh_entity_data["x"] = float(x)
        if y is not None:
            sprite.center_y = float(y)
            sprite.mesh_entity_data["y"] = float(y)
        if scale is not None:
            sprite.scale = float(scale)
            sprite.mesh_entity_data["scale"] = float(scale)
        if tag is not None:
            sprite.mesh_entity_data["tag"] = tag


def _build_controller(payload: dict, monkeypatch) -> tuple[EditorModeController, _StubSprite]:
    monkeypatch.setattr(editor_module, "PREFAB_PALETTE", [])
    monkeypatch.setattr(editor_module, "load_prefab_palette", lambda *a, **k: [])

    sprite = _StubSprite(payload["entities"][0])
    scene_controller = _StubSceneController(payload, [sprite])
    window = SimpleNamespace(strict_mode=False, scene_controller=scene_controller, width=800, height=600)
    controller = EditorModeController(as_any(window))
    controller.active = True
    as_any(controller).selected_entity = sprite
    return controller, sprite


def test_revert_prefab_override_marks_dirty(monkeypatch) -> None:
    payload = {
        "entities": [
            {
                "id": "e1",
                "prefab_id": "crate",
                "scale": 1.2,
                "prefab_overrides": {"scale": 1.2},
            }
        ]
    }
    controller, sprite = _build_controller(payload, monkeypatch)
    monkeypatch.setattr(controller, "_get_prefab_base_entity", lambda _data: {"scale": 1.0})

    row = DiffRow(key="scale", base_value=1.0, override_value=1.2, effective_value=1.2)
    assert controller.dirty_state.is_dirty is False
    assert controller._entity_panels_revert_prefab_override(row) is True
    assert controller.dirty_state.is_dirty is True
    assert sprite.mesh_entity_data["scale"] == 1.0
    assert "prefab_overrides" not in sprite.mesh_entity_data
