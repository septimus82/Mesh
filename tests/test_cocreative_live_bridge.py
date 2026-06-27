from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from engine.editor.live_session_bridge import (
    EditorLiveSessionBridge,
    LiveSessionInfo,
    session_file_path,
    write_live_session_file,
)
from engine.mcp_server import tools
from tests.test_cocreative_live_ops import _entity_names, _make_controller


def _write_session_payload(root: Path, payload: dict[str, Any]) -> None:
    path = session_file_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _call_live_add_with_drain(controller: Any, bridge: EditorLiveSessionBridge, root: Path, **kwargs: Any) -> dict[str, Any]:
    container: dict[str, Any] = {}

    def call_tool() -> None:
        container["result"] = tools.live_add_entity_from_prefab(root=str(root), **kwargs)

    thread = threading.Thread(target=call_tool)
    thread.start()
    deadline = time.time() + 3.0
    while bridge.pending_count() == 0 and thread.is_alive() and time.time() < deadline:
        time.sleep(0.01)

    assert bridge.pending_count() > 0
    assert len(controller.window.scene_controller.all_sprites) == 0

    while thread.is_alive() and time.time() < deadline:
        controller.drain_live_bridge()
        time.sleep(0.01)
    thread.join(timeout=1.0)
    assert not thread.is_alive()
    return container["result"]


def test_live_add_entity_from_prefab_forwards_to_running_editor_without_file_write(tmp_path: Path) -> None:
    controller = _make_controller()
    scene_controller = controller.window.scene_controller
    bridge = EditorLiveSessionBridge(controller, tmp_path)
    bridge.start(write_discovery=True)
    try:
        result = _call_live_add_with_drain(
            controller,
            bridge,
            tmp_path,
            prefab_id="crate",
            x=64,
            y=80,
            name="bridge_crate",
        )

        assert result["ok"] is True
        assert result["mode"] == "live_editor"
        assert len(scene_controller.all_sprites) == 1
        assert "bridge_crate" in _entity_names(scene_controller.build_scene_snapshot(compact=False))
        assert scene_controller._loaded_scene_data["entities"][0]["name"] == "bridge_crate"
        assert len(controller.undo.undo_stack) == 1
        assert controller.undo.undo_stack[0]["type"] == "ApplyAIOpBatch"
        assert not (tmp_path / "scenes" / "live.json").exists()
    finally:
        bridge.stop()


def test_live_add_entity_without_discovery_returns_no_live_session_without_apply_ops(
    tmp_path: Path, monkeypatch: Any
) -> None:
    def fail_apply_ops(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("file-backed apply_ops must not be called")

    monkeypatch.setattr(tools, "apply_ops", fail_apply_ops)

    result = tools.live_add_entity_from_prefab("crate", 64, 80, root=str(tmp_path))

    assert result == {"ok": False, "mode": "live_editor", "reason": "no_live_session"}


def test_live_session_discovery_rejects_non_loopback_host(tmp_path: Path) -> None:
    info = LiveSessionInfo(
        schema_version=1,
        workspace_root=str(tmp_path.resolve()),
        host="0.0.0.0",
        port=12345,
        pid=1,
        session_id="session",
        token="token",
        current_scene_path="scenes/live.json",
        started_at=time.time(),
    )
    write_live_session_file(tmp_path, info)

    result = tools.live_add_entity_from_prefab("crate", 64, 80, root=str(tmp_path))

    assert result["ok"] is False
    assert result["reason"] == "invalid_live_session"


def test_live_session_discovery_rejects_bad_and_missing_token(tmp_path: Path) -> None:
    controller = _make_controller()
    bridge = EditorLiveSessionBridge(controller, tmp_path)
    info = bridge.start(write_discovery=True)
    try:
        bad_token = info.to_dict()
        bad_token["token"] = "bad-token"
        _write_session_payload(tmp_path, bad_token)
        result = tools.live_add_entity_from_prefab("crate", 64, 80, root=str(tmp_path))
        assert result["ok"] is False

        missing_token = info.to_dict()
        missing_token.pop("token")
        _write_session_payload(tmp_path, missing_token)
        result = tools.live_add_entity_from_prefab("crate", 64, 80, root=str(tmp_path))
        assert result["ok"] is False
        assert result["reason"] == "invalid_live_session"
    finally:
        bridge.stop()


def test_live_session_discovery_rejects_workspace_mismatch(tmp_path: Path) -> None:
    controller = _make_controller()
    bridge = EditorLiveSessionBridge(controller, tmp_path)
    info = bridge.start(write_discovery=True)
    try:
        payload = info.to_dict()
        payload["workspace_root"] = str((tmp_path / "other").resolve())
        _write_session_payload(tmp_path, payload)

        result = tools.live_add_entity_from_prefab("crate", 64, 80, root=str(tmp_path))

        assert result["ok"] is False
        assert result["reason"] == "workspace_mismatch"
    finally:
        bridge.stop()


def test_live_session_discovery_rejects_failed_health(tmp_path: Path) -> None:
    info = LiveSessionInfo(
        schema_version=1,
        workspace_root=str(tmp_path.resolve()),
        host="127.0.0.1",
        port=9,
        pid=1,
        session_id="session",
        token="token",
        current_scene_path="scenes/live.json",
        started_at=time.time(),
    )
    write_live_session_file(tmp_path, info)

    result = tools.live_add_entity_from_prefab("crate", 64, 80, root=str(tmp_path))

    assert result == {"ok": False, "mode": "live_editor", "reason": "no_live_session"}
