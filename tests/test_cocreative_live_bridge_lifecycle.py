from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib import request

from engine.editor.live_session_bridge import read_live_session_file
from tests.test_cocreative_live_ops import _make_controller


def _health(root: Path) -> dict[str, Any]:
    session = read_live_session_file(root)
    assert session is not None
    req = request.Request(
        f"http://{session['host']}:{session['port']}/health",
        method="GET",
        headers={"Authorization": f"Bearer {session['token']}"},
    )
    with request.urlopen(req, timeout=2.0) as response:  # noqa: S310 - test reads loopback session written by bridge.
        payload = json.loads(response.read().decode("utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_interactive_editor_activation_starts_bridge_and_teardown_removes_discovery(tmp_path: Path) -> None:
    controller = _make_controller()
    controller._repo_root_override = tmp_path
    controller.window._mesh_live_bridge_interactive = True
    controller.window.scene_controller.current_scene_path = "scenes/live_activation.json"

    controller._enable_editor_mode()
    try:
        bridge = controller.live_bridge
        assert bridge is not None
        session = read_live_session_file(tmp_path)
        assert session is not None
        assert session["workspace_root"] == str(tmp_path.resolve())
        assert session["current_scene_path"] == "scenes/live_activation.json"
        assert _health(tmp_path)["current_scene_path"] == "scenes/live_activation.json"
    finally:
        controller._disable_editor_mode()

    assert controller.live_bridge is None
    assert read_live_session_file(tmp_path) is None


def test_non_interactive_editor_activation_does_not_start_bridge(tmp_path: Path) -> None:
    controller = _make_controller()
    controller._repo_root_override = tmp_path

    controller._enable_editor_mode()
    try:
        assert controller.live_bridge is None
        assert read_live_session_file(tmp_path) is None
    finally:
        controller._disable_editor_mode()


def test_config_flag_can_disable_interactive_live_bridge(tmp_path: Path) -> None:
    controller = _make_controller()
    controller._repo_root_override = tmp_path
    controller.window._mesh_live_bridge_interactive = True
    controller.window.engine_config = SimpleNamespace(cocreative_live_bridge_enabled=False)

    controller._enable_editor_mode()
    try:
        assert controller.live_bridge is None
        assert read_live_session_file(tmp_path) is None
    finally:
        controller._disable_editor_mode()


def test_scene_switch_refreshes_live_session_discovery_and_health(tmp_path: Path) -> None:
    controller = _make_controller()
    controller._repo_root_override = tmp_path
    controller.window._mesh_live_bridge_interactive = True
    controller.window.scene_controller.current_scene_path = "scenes/a.json"
    controller._enable_editor_mode()
    try:
        controller.window.scene_controller.current_scene_path = "scenes/b.json"
        controller.refresh_live_bridge_scene()

        session = read_live_session_file(tmp_path)
        assert session is not None
        assert session["current_scene_path"] == "scenes/b.json"
        assert _health(tmp_path)["current_scene_path"] == "scenes/b.json"
    finally:
        controller._disable_editor_mode()


def test_bridge_start_failure_is_swallowed_and_editor_still_activates(tmp_path: Path, monkeypatch: Any) -> None:
    controller = _make_controller()
    controller._repo_root_override = tmp_path
    controller.window._mesh_live_bridge_interactive = True

    def fail_start(self: Any) -> None:  # noqa: ANN001
        raise OSError("bind failed")

    monkeypatch.setattr("engine.editor.live_session_bridge.EditorLiveSessionBridge.start", fail_start)

    controller._enable_editor_mode()
    try:
        assert controller.active is True
        assert controller.live_bridge is None
        assert read_live_session_file(tmp_path) is None
    finally:
        controller._disable_editor_mode()
