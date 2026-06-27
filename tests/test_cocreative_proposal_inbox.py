from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from engine.editor.dock_tab_registry import DOCK_TAB_TOOLTIPS, RIGHT_DOCK_TABS
from engine.editor.editor_dock_controller import EditorDockController
from engine.editor.live_session_bridge import EditorLiveSessionBridge
from engine.editor.proposal_inbox import ProposalInbox
from tests.test_cocreative_live_bridge import _stage_with_drain
from tests.test_cocreative_live_ops import _entity_by_name, _entity_names, _guard_add_op, _make_controller


def _guard_patrol_ops(name: str) -> list[dict[str, Any]]:
    return [
        _guard_add_op(name),
        {
            "type": "set_behaviour_params",
            "entity_id": name,
            "behaviour_name": "Patrol",
            "params": {"speed": 2.5, "points": [[0, 0], [32, 0]]},
        },
    ]


def test_proposal_inbox_lists_two_staged_bridge_proposals_without_mutation(tmp_path: Path) -> None:
    controller = _make_controller()
    scene_controller = controller.window.scene_controller
    bridge = EditorLiveSessionBridge(controller, tmp_path)
    bridge.start(write_discovery=True)
    try:
        first = _stage_with_drain(controller, bridge, tmp_path, _guard_patrol_ops("inbox_guard_a"))
        second = _stage_with_drain(controller, bridge, tmp_path, [_guard_add_op("inbox_guard_b")])

        inbox = controller.proposal_inbox
        pending = inbox.list_pending()

        assert first["proposal_id"]
        assert second["proposal_id"]
        assert [row["proposal_id"] for row in pending] == [first["proposal_id"], second["proposal_id"]]
        assert all(row["dry_run"]["ok"] is True for row in pending)
        assert "inbox_guard_a" in pending[0]["preview_summary"]
        assert "inbox_guard_b" in pending[1]["preview_summary"]
        assert len(scene_controller.all_sprites) == 0
        assert scene_controller._loaded_scene_data["entities"] == []
        assert controller.undo.undo_stack == []
    finally:
        bridge.stop()


def test_proposal_inbox_accept_applies_batch_as_one_undoable_command(tmp_path: Path) -> None:
    controller = _make_controller()
    scene_controller = controller.window.scene_controller
    bridge = EditorLiveSessionBridge(controller, tmp_path)
    bridge.start(write_discovery=True)
    try:
        staged = _stage_with_drain(controller, bridge, tmp_path, _guard_patrol_ops("accepted_inbox_guard"))
        inbox = controller.proposal_inbox

        result = inbox.accept(staged["proposal_id"])

        assert result["ok"] is True
        assert staged["proposal_id"] not in {row["proposal_id"] for row in inbox.list_pending()}
        assert len(scene_controller.all_sprites) == 1
        payload = _entity_by_name(scene_controller.build_scene_snapshot(compact=False), "accepted_inbox_guard")
        assert payload["behaviour_config"]["Patrol"]["speed"] == 2.5
        assert len(controller.undo.undo_stack) == 1
        assert controller.undo.undo_stack[0]["type"] == "ApplyAIOpBatch"
        assert len(controller.undo.undo_stack[0]["children"]) == 2

        assert controller.undo.undo() is True
        assert len(scene_controller.all_sprites) == 0
        assert "accepted_inbox_guard" not in _entity_names(scene_controller.build_scene_snapshot(compact=False))
    finally:
        bridge.stop()


def test_proposal_inbox_reject_drops_without_mutation_or_undo(tmp_path: Path) -> None:
    controller = _make_controller()
    scene_controller = controller.window.scene_controller
    bridge = EditorLiveSessionBridge(controller, tmp_path)
    bridge.start(write_discovery=True)
    try:
        staged = _stage_with_drain(controller, bridge, tmp_path, [_guard_add_op("rejected_inbox_guard")])
        inbox = controller.proposal_inbox
        revision = controller.content_revision

        result = inbox.reject(staged["proposal_id"])

        assert result["ok"] is True
        assert inbox.list_pending() == []
        assert len(scene_controller.all_sprites) == 0
        assert scene_controller._loaded_scene_data["entities"] == []
        assert controller.undo.undo_stack == []
        assert controller.content_revision == revision
    finally:
        bridge.stop()


def test_proposal_inbox_empty_without_bridge() -> None:
    controller = _make_controller()
    controller.live_bridge = None

    assert ProposalInbox(controller).list_pending() == []


def test_ai_proposals_dock_is_registered_and_toggleable() -> None:
    assert "AI Proposals" in RIGHT_DOCK_TABS
    assert "AI Proposals" in DOCK_TAB_TOOLTIPS

    class HostStub:
        def __init__(self) -> None:
            self.active = True
            self._menu_active = None
            self.entity_panels_active = False
            self.entity_panels_focus = ""
            self.asset_browser_active = False
            self.problems = SimpleNamespace(preview_open=False, close_preview=lambda _host: None)
            self.panels = SimpleNamespace(close_context_menu=lambda: None)
            self.search = SimpleNamespace(sync_search_focus=lambda: None)
            self.autosaved = False

        def _autosave_workspace(self) -> None:
            self.autosaved = True

    dock = EditorDockController(None, left_tab="Outliner", right_tab="Inspector")
    host = HostStub()

    assert dock.apply_tab_change(host, "right", "AI Proposals") is True
    assert dock.right_tab == "AI Proposals"
    assert host.autosaved is True
