from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import engine.editor_controller as editor_module
import engine.optional_arcade as optional_arcade
from engine.editor.editor_overlay_controller import EditorOverlayController
from engine.editor_commands import run_command
from engine.editor_controller import EditorModeController
from engine.game_runtime import input_dispatch
from tests._typing import as_any

pytestmark = pytest.mark.fast


class _StubSprite(SimpleNamespace):
    def __init__(self, entity_data: dict[str, Any]) -> None:
        super().__init__(
            mesh_entity_data=entity_data,
            mesh_name=entity_data.get("mesh_name") or entity_data.get("name") or entity_data.get("id") or "",
            center_x=float(entity_data.get("x", 0.0) or 0.0),
            center_y=float(entity_data.get("y", 0.0) or 0.0),
            angle=float(entity_data.get("rotation", 0.0) or 0.0),
            mesh_tag=entity_data.get("tag"),
        )


class _StubSceneController:
    def __init__(self, payload: dict[str, Any], sprites: list[_StubSprite], scene_path: str) -> None:
        self._loaded_scene_data = payload
        self.current_scene_path = scene_path
        self.all_sprites = sprites

    def _ensure_entity_data_dict(self, sprite: _StubSprite) -> dict[str, Any]:
        return as_any(sprite.mesh_entity_data)

    def _find_player_sprite(self) -> _StubSprite | None:
        return self.all_sprites[0] if self.all_sprites else None

    def _apply_entity_mutation(self, sprite: _StubSprite, *, x: float | None = None, y: float | None = None) -> None:
        if x is not None:
            sprite.center_x = float(x)
            sprite.mesh_entity_data["x"] = float(x)
        if y is not None:
            sprite.center_y = float(y)
            sprite.mesh_entity_data["y"] = float(y)

    def build_scene_snapshot(self) -> dict[str, Any]:
        return self._loaded_scene_data


class _StubCamera(SimpleNamespace):
    def __init__(self) -> None:
        super().__init__(position=(0.0, 0.0))

    def move_to(self, pos: tuple[float, float], _speed: float = 1.0) -> None:
        self.position = (float(pos[0]), float(pos[1]))


def _build_controller(monkeypatch: pytest.MonkeyPatch, scene_path: str) -> EditorModeController:
    monkeypatch.setattr(editor_module, "PREFAB_PALETTE", [])
    monkeypatch.setattr(editor_module, "load_prefab_palette", lambda *a, **k: [])

    payload = {"entities": [{"id": "player_01", "x": 0.0, "y": 0.0, "tag": "player"}]}
    sprite = _StubSprite(payload["entities"][0])
    scene_controller = _StubSceneController(payload, [sprite], scene_path)
    window = SimpleNamespace(
        strict_mode=False,
        scene_controller=scene_controller,
        width=800,
        height=600,
        paused=True,
        camera=_StubCamera(),
        get_camera_center=lambda: (24.0, 48.0),
    )
    controller = EditorModeController(as_any(window))
    controller.active = True
    as_any(controller).selected_entity = sprite
    return controller


def test_command_palette_play_start_runs_play_from_here() -> None:
    calls: list[str] = []
    window = SimpleNamespace(editor_controller=SimpleNamespace(play_from_here=lambda: calls.append("play")))

    assert run_command("editor.play.start", window) is True

    assert calls == ["play"]


def test_runtime_f6_routes_to_playtest_instead_of_asset_reload() -> None:
    calls: list[str] = []
    window = SimpleNamespace(
        editor_controller=SimpleNamespace(active=True, play_from_here=lambda: calls.append("play")),
        console_controller=SimpleNamespace(active=False),
        ui_controller=SimpleNamespace(on_key_press=lambda *_args: False),
        input_controller=SimpleNamespace(on_key_press=lambda *_args: calls.append("input")),
        game_over=False,
        console_log=lambda message: calls.append(str(message)),
    )

    input_dispatch.on_key_press(as_any(window), optional_arcade.arcade.key.F6, 0)

    assert calls == ["play"]


def test_playtesting_overlay_draws_visible_status(monkeypatch: pytest.MonkeyPatch) -> None:
    drawn: list[str] = []
    monkeypatch.setattr("engine.editor.editor_overlay_controller._draw_rectangle_filled", lambda *a, **k: None)
    monkeypatch.setattr(
        "engine.editor.editor_overlay_controller.optional_arcade.arcade.draw_text",
        lambda text, *a, **k: drawn.append(str(text)),
    )
    editor = SimpleNamespace(
        active=False,
        play_session=SimpleNamespace(is_playing=True),
        window=SimpleNamespace(width=800, height=600),
    )

    EditorOverlayController(editor).draw_overlay()

    assert "Playtesting..." in drawn
    assert "Press Esc to return to editor" in drawn


def test_escape_during_playtest_stops_before_settings_or_pause() -> None:
    calls: list[str] = []
    session = SimpleNamespace(is_playing=True)

    def _stop() -> None:
        calls.append("stop")
        session.is_playing = False

    window = SimpleNamespace(
        editor_controller=SimpleNamespace(play_session=session, stop_playing=_stop),
        console_controller=SimpleNamespace(active=False),
        ui_controller=SimpleNamespace(on_key_press=lambda *_args: False),
        settings_overlay=SimpleNamespace(toggle=lambda: calls.append("settings")),
        input_controller=SimpleNamespace(on_key_press=lambda *_args: calls.append("input")),
        game_over=False,
        paused=False,
        pause_menu=SimpleNamespace(toggle=lambda: calls.append("pause_toggle"), visible=False),
        console_log=lambda _message: calls.append("console"),
    )

    input_dispatch.on_key_press(as_any(window), optional_arcade.arcade.key.ESCAPE, 0)

    assert calls == ["stop"]
    assert session.is_playing is False


def test_dirty_playtest_prompt_uses_custom_labels(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    controller = _build_controller(monkeypatch, str(tmp_path / "scene.json"))
    controller._mark_dirty()

    assert controller.play_from_here() is False

    assert controller.confirm_open is True
    assert controller.unsaved_confirm.labels == (
        "Save and Playtest",
        "Playtest Without Saving",
        "Cancel",
    )


def test_save_and_playtest_saves_then_enters_playtest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scene_path = tmp_path / "scene.json"
    controller = _build_controller(monkeypatch, str(scene_path))
    controller._mark_dirty()
    controller.play_from_here()

    controller.confirm_selection_index = 0
    controller._handle_unsaved_confirm_input(optional_arcade.arcade.key.ENTER, 0)

    assert controller.play_session.is_playing is True
    assert controller.dirty_state.is_dirty is False
    assert json.loads(scene_path.read_text(encoding="utf-8"))["entities"][0]["id"] == "player_01"


def test_playtest_without_saving_enters_playtest_and_keeps_dirty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scene_path = tmp_path / "scene.json"
    controller = _build_controller(monkeypatch, str(scene_path))
    controller._mark_dirty()
    controller.play_from_here()

    controller.confirm_selection_index = 1
    controller._handle_unsaved_confirm_input(optional_arcade.arcade.key.ENTER, 0)

    assert controller.play_session.is_playing is True
    assert controller.dirty_state.is_dirty is True
    assert not scene_path.exists()


def test_cancel_playtest_prompt_keeps_dirty_and_editor_active(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    controller = _build_controller(monkeypatch, str(tmp_path / "scene.json"))
    controller._mark_dirty()
    controller.play_from_here()

    controller._handle_unsaved_confirm_input(optional_arcade.arcade.key.ESCAPE, 0)

    assert controller.play_session.is_playing is False
    assert controller.dirty_state.is_dirty is True
    assert controller.active is True
