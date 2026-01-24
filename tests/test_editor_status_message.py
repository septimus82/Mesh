from __future__ import annotations

from types import SimpleNamespace

import engine.editor_controller as editor_module
from engine.editor_controller import EditorModeController


def test_editor_status_message_expires(monkeypatch) -> None:
    monkeypatch.setattr(editor_module, "PREFAB_PALETTE", [])
    monkeypatch.setattr(editor_module, "load_prefab_palette", lambda *a, **k: [])

    now = {"t": 100.0}
    monkeypatch.setattr("engine.editor_controller.time.time", lambda: now["t"])

    window = SimpleNamespace()
    window.strict_mode = False
    window.paused = False
    window.width = 800
    window.height = 600
    window.scene_controller = SimpleNamespace(current_scene_path="scenes/test.json")
    window.screen_to_world = lambda x, y: (float(x), float(y))
    window.camera_controller = SimpleNamespace(zoom=1.0)

    controller = EditorModeController(window)  # type: ignore[arg-type]
    controller.active = True

    controller.set_status("hello", seconds=0.5)
    assert controller._status_message == "hello"

    now["t"] = 101.0
    controller._update_status()
    assert controller._status_message is None
