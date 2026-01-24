from __future__ import annotations

import json
from pathlib import Path

from engine.game_runtime import scene_ops


class _StubSceneController:
    def __init__(self, scene_path: Path) -> None:
        self.current_scene_path = str(scene_path)
        self._last_hot_reload_error_message = ""
        self._last_hot_reload_error_scene = ""


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

    def reload_scene(self, new_path: str | None = None) -> bool:  # noqa: ARG002
        self.scene_controller._last_hot_reload_error_message = "ValueError: invalid JSON"
        return False

    def clear_hot_reload_error(self) -> None:
        self.hot_reload_error_message = ""
        self.hot_reload_error_scene_path = ""
        self.hot_reload_error_visible = False

    def set_hot_reload_error(self, message: str, scene_path: str | None = None) -> None:
        self.hot_reload_error_message = str(message or "").strip()
        self.hot_reload_error_scene_path = str(scene_path or "").strip()
        self.hot_reload_error_visible = bool(self.hot_reload_error_message)


def test_hot_reload_scene_failure(tmp_path: Path) -> None:
    scene_path = tmp_path / "scene.json"
    scene_path.write_text(json.dumps({"entities": [{"id": "a"}]}), encoding="utf-8")

    controller = _StubSceneController(scene_path)
    window = _StubWindow(controller)

    ok = scene_ops.reload_scene_from_disk(window)

    assert ok is False
    assert window.hot_reload_error_visible is True
    assert "invalid JSON" in window.hot_reload_error_message
