from __future__ import annotations

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
    def __init__(self, sprite: _StubSprite, scene_path: str) -> None:
        self.current_scene_path = scene_path
        self._loaded_scene_data = {"entities": [sprite.mesh_entity_data]}
        self.all_sprites = [sprite]

    def _find_player_sprite(self) -> _StubSprite | None:
        return self.all_sprites[0] if self.all_sprites else None

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


class _StubCamera(SimpleNamespace):
    def __init__(self) -> None:
        super().__init__(position=(0.0, 0.0))

    def move_to(self, pos, _speed: float = 1.0) -> None:
        self.position = (float(pos[0]), float(pos[1]))


def _build_controller(monkeypatch, scene_path: str = "packs/core/scenes/test_scene.json") -> tuple[EditorModeController, _StubSprite, SimpleNamespace]:
    monkeypatch.setattr(editor_module, "PREFAB_PALETTE", [])
    monkeypatch.setattr(editor_module, "load_prefab_palette", lambda *a, **k: [])

    sprite = _StubSprite({"id": "player_01", "x": 0.0, "y": 0.0, "tag": "player"})
    scene_controller = _StubSceneController(sprite, scene_path)
    window = SimpleNamespace(
        strict_mode=False,
        scene_controller=scene_controller,
        width=800,
        height=600,
        paused=True,
        camera=_StubCamera(),
    )
    window.get_camera_center = lambda: (64.0, 96.0)
    controller = EditorModeController(window)  # type: ignore[arg-type]
    controller.active = True
    controller.selected_entity = sprite  # type: ignore[assignment]
    return controller, sprite, window


def test_play_from_here_starts_session_and_spawns(monkeypatch) -> None:
    controller, sprite, window = _build_controller(monkeypatch)
    window.get_camera_center = lambda: (120.0, 80.0)

    started = controller.play_from_here()

    assert started is True
    assert controller.play_session.is_playing is True
    assert controller.play_session.return_scene_id == "packs/core/scenes/test_scene.json"
    assert controller.play_session.return_camera_pos == (120.0, 80.0)
    assert controller.play_session.return_selection is sprite
    assert controller.active is False
    assert window.paused is False
    assert sprite.center_x == 120.0
    assert sprite.center_y == 80.0


def test_stop_restores_editor_state(monkeypatch) -> None:
    controller, sprite, window = _build_controller(monkeypatch)
    window.get_camera_center = lambda: (32.0, 48.0)

    controller.play_from_here()
    controller.selected_entity = None
    window.camera.position = (0.0, 0.0)

    stopped = controller.stop_playing()

    assert stopped is True
    assert controller.play_session.is_playing is False
    assert controller.active is True
    assert window.paused is True
    assert window.camera.position == (32.0, 48.0)
    assert controller.selected_entity is sprite


def test_play_from_here_dirty_guard_blocks_until_confirm(monkeypatch) -> None:
    controller, _sprite, _window = _build_controller(monkeypatch)
    controller._mark_dirty()

    started = controller.play_from_here()

    assert started is False
    assert controller.play_session.is_playing is False
    assert controller.confirm_open is True

    controller.confirm_selection_index = 1
    controller._handle_unsaved_confirm_input(optional_arcade.arcade.key.ENTER, 0)

    assert controller.play_session.is_playing is True
    assert controller.confirm_open is False
    assert controller.dirty_state.is_dirty is False


def test_stop_requests_scene_restore_when_changed(monkeypatch) -> None:
    controller, _sprite, window = _build_controller(monkeypatch)
    calls: list[str] = []
    window.request_scene_change = calls.append
    controller.play_from_here()
    window.scene_controller.current_scene_path = "packs/bonus/scenes/other_scene.json"

    controller.stop_playing()

    assert calls == ["packs/core/scenes/test_scene.json"]
