from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path

import engine.editor_controller as editor_module
from engine.editor_controller import EditorModeController
from tests._editor_window_stub import EditorWindowStub, as_game_window
from tests._typing import as_any


class _StubSprite(SimpleNamespace):
    def __init__(self, entity_data: dict) -> None:
        super().__init__(
            mesh_entity_data=entity_data,
            mesh_name=entity_data.get("mesh_name") or entity_data.get("name") or entity_data.get("id") or "",
            center_x=float(entity_data.get("x", 0.0) or 0.0),
            center_y=float(entity_data.get("y", 0.0) or 0.0),
            angle=float(entity_data.get("rotation", 0.0) or 0.0),
            mesh_tag=entity_data.get("tag"),
        )


class _StubSceneController:
    def __init__(self, payload: dict, sprites: list[_StubSprite], scene_path: str) -> None:
        self._loaded_scene_data = payload
        self.current_scene_path = scene_path
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
            sprite.mesh_entity_data["scale"] = float(scale)
        if tag is not None:
            sprite.mesh_tag = tag
            sprite.mesh_entity_data["tag"] = tag

    def build_scene_snapshot(self) -> dict:
        return self._loaded_scene_data


def _build_controller(payload: dict, scene_path: str, monkeypatch) -> tuple[EditorModeController, _StubSprite]:
    monkeypatch.setattr(editor_module, "PREFAB_PALETTE", [])
    monkeypatch.setattr(editor_module, "load_prefab_palette", lambda *a, **k: [])

    sprite = _StubSprite(payload["entities"][0])
    scene_controller = _StubSceneController(payload, [sprite], scene_path)
    window = EditorWindowStub(scene_controller=scene_controller)
    controller = EditorModeController(as_game_window(window))
    controller.active = True
    as_any(controller).selected_entity = sprite
    return controller, sprite


def test_edit_operation_sets_dirty(monkeypatch) -> None:
    payload = {"entities": [{"id": "e1", "x": 1.0, "y": 2.0, "mesh_name": "Hero"}]}
    controller, _sprite = _build_controller(payload, "", monkeypatch)

    assert controller.dirty_state.is_dirty is False
    assert controller._entity_panels_apply_field_update("x", 5.0) is True
    assert controller.dirty_state.is_dirty is True


def test_save_clears_dirty_and_writes_json(tmp_path: Path, monkeypatch) -> None:
    repo_root = tmp_path
    monkeypatch.setenv("MESH_REPO_ROOT", str(repo_root))
    monkeypatch.chdir(repo_root)

    scene_path = Path("scenes/test_scene.json")
    (repo_root / "scenes").mkdir(parents=True, exist_ok=True)
    payload = {"name": "TestScene", "entities": [{"id": "e1", "x": 0.0, "y": 0.0}]}
    controller, _sprite = _build_controller(payload, str(scene_path), monkeypatch)

    controller._mark_dirty()
    controller.save_current_scene()

    assert controller.dirty_state.is_dirty is False
    written = json.loads((repo_root / scene_path).read_text(encoding="utf-8"))
    assert written == payload
