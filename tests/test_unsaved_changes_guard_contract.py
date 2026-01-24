from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import engine.editor_controller as editor_module
import engine.optional_arcade as optional_arcade
from engine.editor_controller import EditorModeController


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

    def build_scene_snapshot(self) -> dict:
        return self._loaded_scene_data


def _build_controller(payload: dict, scene_path: str, monkeypatch) -> EditorModeController:
    monkeypatch.setattr(editor_module, "PREFAB_PALETTE", [])
    monkeypatch.setattr(editor_module, "load_prefab_palette", lambda *a, **k: [])

    sprite = _StubSprite(payload["entities"][0])
    scene_controller = _StubSceneController(payload, [sprite], scene_path)
    window = SimpleNamespace(strict_mode=False, scene_controller=scene_controller, width=800, height=600)
    controller = EditorModeController(window)  # type: ignore[arg-type]
    controller.active = True
    controller.selected_entity = sprite  # type: ignore[assignment]
    return controller


def test_dirty_action_opens_modal(monkeypatch) -> None:
    payload = {"entities": [{"id": "e1", "x": 1.0, "y": 2.0}]}
    controller = _build_controller(payload, "", monkeypatch)
    controller._mark_dirty()

    calls: list[str] = []
    blocked = controller.confirm_unsaved_changes("Switch Scene", lambda: calls.append("ran"))

    assert blocked is True
    assert controller.confirm_open is True
    assert calls == []


def test_save_executes_action_and_writes_json(tmp_path: Path, monkeypatch) -> None:
    scene_path = tmp_path / "scenes" / "test_scene.json"
    scene_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"name": "Scene", "entities": [{"id": "e1", "x": 0.0, "y": 0.0}]}
    controller = _build_controller(payload, str(scene_path), monkeypatch)
    controller._mark_dirty()

    calls: list[str] = []
    controller.confirm_unsaved_changes("Switch Scene", lambda: calls.append("ran"))

    controller._handle_unsaved_confirm_input(optional_arcade.arcade.key.ENTER, 0)

    assert calls == ["ran"]
    assert controller.dirty_state.is_dirty is False
    written = json.loads(scene_path.read_text(encoding="utf-8"))
    assert written == payload


def test_discard_executes_action_and_clears_dirty(tmp_path: Path, monkeypatch) -> None:
    scene_path = tmp_path / "scenes" / "discard_scene.json"
    scene_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"entities": [{"id": "e1", "x": 3.0, "y": 4.0}]}
    controller = _build_controller(payload, str(scene_path), monkeypatch)
    controller._mark_dirty()

    calls: list[str] = []
    controller.confirm_unsaved_changes("Exit Editor Mode", lambda: calls.append("ran"))
    controller.confirm_selection_index = 1
    controller._handle_unsaved_confirm_input(optional_arcade.arcade.key.ENTER, 0)

    assert calls == ["ran"]
    assert controller.dirty_state.is_dirty is False
    assert not scene_path.exists()


def test_cancel_closes_modal_and_keeps_dirty(monkeypatch) -> None:
    payload = {"entities": [{"id": "e1", "x": 1.0, "y": 2.0}]}
    controller = _build_controller(payload, "", monkeypatch)
    controller._mark_dirty()

    calls: list[str] = []
    controller.confirm_unsaved_changes("Switch Scene", lambda: calls.append("ran"))
    controller._handle_unsaved_confirm_input(optional_arcade.arcade.key.ESCAPE, 0)

    assert controller.confirm_open is False
    assert controller.dirty_state.is_dirty is True
    assert calls == []
