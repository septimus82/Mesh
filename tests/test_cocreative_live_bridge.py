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
from tests.test_cocreative_live_ops import _entity_by_name, _entity_names, _guard_add_op, _make_controller


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


def _call_tool_with_drain(
    controller: Any,
    bridge: EditorLiveSessionBridge,
    call_tool: Any,
    *,
    expect_queued: bool = True,
) -> dict[str, Any]:
    container: dict[str, Any] = {}

    def run() -> None:
        container["result"] = call_tool()

    thread = threading.Thread(target=run)
    thread.start()
    deadline = time.time() + 3.0
    while bridge.pending_count() == 0 and thread.is_alive() and time.time() < deadline:
        time.sleep(0.01)
    if expect_queued:
        assert bridge.pending_count() > 0
    while thread.is_alive() and time.time() < deadline:
        controller.drain_live_bridge()
        time.sleep(0.01)
    thread.join(timeout=1.0)
    assert not thread.is_alive()
    return container["result"]


def _stage_with_drain(
    controller: Any,
    bridge: EditorLiveSessionBridge,
    root: Path,
    ops: list[dict[str, Any]],
) -> dict[str, Any]:
    return _call_tool_with_drain(
        controller,
        bridge,
        lambda: tools.live_stage_proposal(ops, root=str(root)),
    )


def _accept_with_drain(controller: Any, bridge: EditorLiveSessionBridge, root: Path, proposal_id: str) -> dict[str, Any]:
    return _call_tool_with_drain(
        controller,
        bridge,
        lambda: tools.live_accept_proposal(proposal_id, root=str(root)),
    )


def _reject_with_drain(controller: Any, bridge: EditorLiveSessionBridge, root: Path, proposal_id: str) -> dict[str, Any]:
    return _call_tool_with_drain(
        controller,
        bridge,
        lambda: tools.live_reject_proposal(proposal_id, root=str(root)),
    )


def _make_marker_root(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "pyproject.toml").write_text("[project]\nname = \"mesh-test\"\n", encoding="utf-8")
    return path


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


def test_live_durable_tools_without_discovery_return_no_live_session_without_apply_ops(
    tmp_path: Path, monkeypatch: Any
) -> None:
    def fail_apply_ops(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("file-backed apply_ops must not be called")

    monkeypatch.setattr(tools, "apply_ops", fail_apply_ops)

    assert tools.live_read_scene(root=str(tmp_path)) == {"ok": False, "mode": "live_editor", "reason": "no_live_session"}
    assert tools.live_stage_proposal([], root=str(tmp_path)) == {
        "ok": False,
        "mode": "live_editor",
        "reason": "no_live_session",
    }
    assert tools.live_accept_proposal("missing", root=str(tmp_path)) == {
        "ok": False,
        "mode": "live_editor",
        "reason": "no_live_session",
    }
    assert tools.live_reject_proposal("missing", root=str(tmp_path)) == {
        "ok": False,
        "mode": "live_editor",
        "reason": "no_live_session",
    }


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


def test_live_stage_accept_yardstick_batch_over_transport_is_one_undoable_command(tmp_path: Path) -> None:
    controller = _make_controller()
    scene_controller = controller.window.scene_controller
    bridge = EditorLiveSessionBridge(controller, tmp_path)
    bridge.start(write_discovery=True)
    try:
        ops = [
            _guard_add_op("bridge_guard"),
            {
                "type": "set_behaviour_params",
                "entity_id": "bridge_guard",
                "behaviour_name": "Patrol",
                "params": {"speed": 2.5, "points": [[0, 0], [32, 0]]},
            },
        ]

        staged = _stage_with_drain(controller, bridge, tmp_path, ops)

        assert staged["ok"] is True
        assert staged["proposal_id"]
        assert staged["dry_run"]["ok"] is True
        assert "bridge_guard" in staged["preview"]
        assert len(scene_controller.all_sprites) == 0
        assert scene_controller._loaded_scene_data["entities"] == []

        accepted = _accept_with_drain(controller, bridge, tmp_path, staged["proposal_id"])

        assert accepted["ok"] is True
        assert len(scene_controller.all_sprites) == 1
        payload = _entity_by_name(scene_controller.build_scene_snapshot(compact=False), "bridge_guard")
        assert payload["behaviour_config"]["Patrol"]["speed"] == 2.5
        assert payload["behaviour_config"]["Patrol"]["points"] == [[0, 0], [32, 0]]
        assert len(controller.undo.undo_stack) == 1
        assert controller.undo.undo_stack[0]["type"] == "ApplyAIOpBatch"
        assert len(controller.undo.undo_stack[0]["children"]) == 2

        assert controller.undo.undo() is True
        assert len(scene_controller.all_sprites) == 0
        assert scene_controller._loaded_scene_data["entities"] == []
        assert "bridge_guard" not in _entity_names(scene_controller.build_scene_snapshot(compact=False))
    finally:
        bridge.stop()


def test_live_reject_proposal_over_transport_drops_without_mutation(tmp_path: Path) -> None:
    controller = _make_controller()
    scene_controller = controller.window.scene_controller
    bridge = EditorLiveSessionBridge(controller, tmp_path)
    bridge.start(write_discovery=True)
    try:
        staged = _stage_with_drain(controller, bridge, tmp_path, [_guard_add_op("rejected_bridge_guard")])
        revision = controller.content_revision

        rejected = _reject_with_drain(controller, bridge, tmp_path, staged["proposal_id"])

        assert rejected["ok"] is True
        assert len(scene_controller.all_sprites) == 0
        assert scene_controller._loaded_scene_data["entities"] == []
        assert controller.undo.undo_stack == []
        assert controller.content_revision == revision

        accepted = _accept_with_drain(controller, bridge, tmp_path, staged["proposal_id"])
        assert accepted["ok"] is False
        assert accepted["reason"] == "proposal_not_found"
    finally:
        bridge.stop()


def test_live_accept_proposal_over_transport_blocks_stale_revision(tmp_path: Path) -> None:
    controller = _make_controller()
    scene_controller = controller.window.scene_controller
    bridge = EditorLiveSessionBridge(controller, tmp_path)
    bridge.start(write_discovery=True)
    try:
        staged = _stage_with_drain(controller, bridge, tmp_path, [_guard_add_op("stale_bridge_guard")])

        human_result = controller.apply_live_op(
            {"type": "add_entity_from_prefab", "prefab_id": "crate", "x": 16, "y": 24, "name": "human_bridge_crate"}
        )
        assert human_result["ok"] is True
        revision_after_human_edit = controller.content_revision

        accepted = _accept_with_drain(controller, bridge, tmp_path, staged["proposal_id"])

        assert accepted["ok"] is False
        assert accepted["data"]["stale"] is True
        assert "human_bridge_crate" in _entity_names(scene_controller.build_scene_snapshot(compact=False))
        assert "stale_bridge_guard" not in _entity_names(scene_controller.build_scene_snapshot(compact=False))
        assert controller.content_revision == revision_after_human_edit
        assert len(controller.undo.undo_stack) == 1
    finally:
        bridge.stop()


def test_live_read_scene_over_transport_reflects_unsaved_live_edit(tmp_path: Path) -> None:
    controller = _make_controller()
    bridge = EditorLiveSessionBridge(controller, tmp_path)
    bridge.start(write_discovery=True)
    try:
        result = controller.apply_live_op(
            {"type": "add_entity_from_prefab", "prefab_id": "crate", "x": 32, "y": 48, "name": "unsaved_bridge_crate"}
        )
        assert result["ok"] is True

        payload = _call_tool_with_drain(
            controller,
            bridge,
            lambda: tools.live_read_scene(compact=False, root=str(tmp_path)),
        )

        assert payload["ok"] is True
        assert payload["mode"] == "live_editor"
        assert payload["dirty"] is True
        assert payload["revision"] == controller.content_revision
        assert "unsaved_bridge_crate" in _entity_names(payload["scene"])
        assert not (tmp_path / "scenes" / "live.json").exists()
    finally:
        bridge.stop()


def test_live_tools_resolve_project_marker_root_from_subdir(tmp_path: Path) -> None:
    root = _make_marker_root(tmp_path / "project")
    subdir = root / "tools" / "nested"
    subdir.mkdir(parents=True)
    controller = _make_controller()
    bridge = EditorLiveSessionBridge(controller, root)
    bridge.start(write_discovery=True)
    try:
        payload = _call_tool_with_drain(
            controller,
            bridge,
            lambda: tools.live_read_scene(compact=False, root=str(subdir)),
        )

        assert payload["ok"] is True
        assert payload["mode"] == "live_editor"
        assert payload["current_scene_path"] == "scenes/live.json"
    finally:
        bridge.stop()


def test_live_tools_report_session_root_mismatch_without_cross_root_connect(tmp_path: Path) -> None:
    editor_root = _make_marker_root(tmp_path / "editor_checkout")
    server_root = _make_marker_root(tmp_path / "server_checkout")
    controller = _make_controller()
    bridge = EditorLiveSessionBridge(controller, editor_root)
    bridge.start(write_discovery=True)
    try:
        result = tools.live_read_scene(root=str(server_root))

        assert result["ok"] is False
        assert result["reason"] == "session_root_mismatch"
        assert result["found_root"] == str(editor_root.resolve())
        assert result["server_root"] == str(server_root.resolve())
        assert "SAME project root" in result["message"]
        assert bridge.pending_count() == 0

        success = _call_tool_with_drain(
            controller,
            bridge,
            lambda: tools.live_read_scene(compact=False, root=str(editor_root)),
        )
        assert success["ok"] is True
    finally:
        bridge.stop()

    empty_root = _make_marker_root(tmp_path / "empty_checkout")
    assert tools.live_read_scene(root=str(empty_root)) == {
        "ok": False,
        "mode": "live_editor",
        "reason": "no_live_session",
    }
