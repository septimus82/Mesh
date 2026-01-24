from __future__ import annotations

import json
from pathlib import Path

from engine.game_runtime import scene_ops


class _StubHUD:
    def __init__(self) -> None:
        self.toasts: list[str] = []

    def enqueue_toast(self, message: str, *, seconds: float = 0.0) -> None:  # noqa: ARG002
        self.toasts.append(str(message))


class _StubSceneController:
    def __init__(self, scene_path: Path) -> None:
        self.current_scene_path = str(scene_path)
        self._loaded_scene_data: dict = {}
        self._last_hot_reload_error_message = ""
        self._last_hot_reload_error_scene = ""

    def load_scene(self, scene_path: str) -> dict:
        data = json.loads(Path(scene_path).read_text(encoding="utf-8"))
        self.current_scene_path = str(scene_path)
        self._loaded_scene_data = data
        return data


class _StubWindow:
    def __init__(self, controller: _StubSceneController) -> None:
        self.scene_controller = controller
        self._undo_suppress_count = 0
        self.scene_dirty = True
        self.scene_dirty_reason = "test"
        self.scene_dirty_counter = 1
        self.hot_reload_error_message = ""
        self.hot_reload_error_scene_path = ""
        self.hot_reload_error_visible = False
        self.player_hud = _StubHUD()

    def reload_scene(self, new_path: str | None = None) -> bool:
        try:
            self.scene_controller.load_scene(new_path or self.scene_controller.current_scene_path)
            self.scene_controller._last_hot_reload_error_message = ""
            return True
        except Exception as exc:  # noqa: BLE001
            self.scene_controller._last_hot_reload_error_message = f"{type(exc).__name__}: {exc}"
            return False

    def clear_hot_reload_error(self) -> None:
        self.hot_reload_error_message = ""
        self.hot_reload_error_scene_path = ""
        self.hot_reload_error_visible = False

    def set_hot_reload_error(self, message: str, scene_path: str | None = None) -> None:
        self.hot_reload_error_message = str(message or "").strip()
        self.hot_reload_error_scene_path = str(scene_path or "").strip()
        self.hot_reload_error_visible = bool(self.hot_reload_error_message)


def test_hot_reload_scene_success(tmp_path: Path) -> None:
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(json.dumps({"entities": [{"id": "a"}]}), encoding="utf-8")

    controller = _StubSceneController(scene_path)
    controller.load_scene(str(scene_path))
    window = _StubWindow(controller)

    scene_path.write_text(json.dumps({"entities": [{"id": "a"}, {"id": "b"}]}), encoding="utf-8")

    ok = scene_ops.reload_scene_from_disk(window)

    assert ok is True
    assert len(controller._loaded_scene_data.get("entities", [])) == 2
    assert window.hot_reload_error_visible is False
    assert "Scene reloaded" in window.player_hud.toasts
