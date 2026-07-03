from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from engine.editor.dock_tab_registry import DOCK_TAB_TOOLTIPS, RIGHT_DOCK_TABS
from engine.editor.editor_dock_controller import EditorDockController
from engine.editor.live_session_bridge import EditorLiveSessionBridge
from engine.editor.proposal_inbox import ProposalInbox
from engine.ui_overlays.proposal_inbox_overlay import ProposalInboxOverlay
from tests.test_cocreative_live_bridge import _stage_with_drain
from engine.editor.creator_mode import build_creator_door_workflow, stage_creator_door_proposal
from engine.editor.creator_mode.creator_door_workflow import CreatorDoorWorkflowRequest
from tests.test_cocreative_live_ops import _entity_by_name, _entity_names, _guard_add_op, _make_controller, _FakeSprite


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


def _creator_door_ops(
    *,
    scene_path: str = "scenes/live.json",
    entity_id: str = "door_north",
    destination_scene: str = "dungeon",
    destination_spawn: str = "north_entry",
) -> list[dict[str, Any]]:
    return [
        {
            "type": "set_behaviour_params",
            "scene_path": scene_path,
            "entity_id": entity_id,
            "behaviour_name": "SceneExit",
            "params": {
                "target_scene": destination_scene,
                "target_spawn": destination_spawn,
                "trigger": "interact",
            },
        }
    ]


def _install_creator_door_entity(controller: Any) -> dict[str, Any]:
    scene_controller = controller.window.scene_controller
    door: dict[str, Any] = {
        "id": "door_north",
        "name": "North Gate",
        "x": 10,
        "y": 20,
        "behaviours": ["SceneExit"],
        "behaviour_config": {
            "SceneExit": {
                "target_scene": "town",
                "target_spawn": "entry",
                "trigger": "interact",
            }
        },
    }
    scene_controller._loaded_scene_data["entities"].append(door)
    scene_controller.add_sprite_to_layer(_FakeSprite(door))
    return door


def _stage_creator_door_with_drain(
    controller: Any,
    bridge: EditorLiveSessionBridge,
    tmp_path: Path,
) -> dict[str, Any]:
    scene_path = str(controller.window.scene_controller.current_scene_path)
    workflow = build_creator_door_workflow(
        CreatorDoorWorkflowRequest(
            source_scene=scene_path,
            destination_scene="dungeon",
            destination_spawn_id="north_entry",
            source_entity_id="door_north",
        )
    )
    container: dict[str, Any] = {}

    def run() -> None:
        container["result"] = stage_creator_door_proposal(workflow, bridge)

    thread = threading.Thread(target=run)
    thread.start()
    deadline = time.time() + 3.0
    while thread.is_alive() and time.time() < deadline:
        controller.drain_live_bridge()
        time.sleep(0.01)
    thread.join(timeout=1.0)
    assert not thread.is_alive()
    result = container["result"]
    assert result.ok is True
    return {"proposal_id": result.proposal_id, "preview": result.preview_summary}


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


def test_ai_proposals_accept_click_dispatches_through_editor_mouse_router(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _make_controller()
    scene_controller = controller.window.scene_controller
    bridge = EditorLiveSessionBridge(controller, tmp_path)
    bridge.start(write_discovery=True)
    try:
        staged = _stage_with_drain(controller, bridge, tmp_path, _guard_patrol_ops("clicked_accept_guard"))
        overlay = _install_and_draw_inbox_overlay(controller, monkeypatch)
        x, y = _button_center(overlay, staged["proposal_id"], "accept")

        handled = controller.handle_mouse_click(x, y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0)

        assert handled is True
        assert controller.proposal_inbox.list_pending() == []
        assert len(scene_controller.all_sprites) == 1
        assert "clicked_accept_guard" in _entity_names(scene_controller.build_scene_snapshot(compact=False))
        assert len(controller.undo.undo_stack) == 1
        assert controller.undo.undo_stack[0]["type"] == "ApplyAIOpBatch"
    finally:
        bridge.stop()


def test_ai_proposals_reject_click_dispatches_through_editor_mouse_router(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _make_controller()
    scene_controller = controller.window.scene_controller
    bridge = EditorLiveSessionBridge(controller, tmp_path)
    bridge.start(write_discovery=True)
    try:
        staged = _stage_with_drain(controller, bridge, tmp_path, [_guard_add_op("clicked_reject_guard")])
        overlay = _install_and_draw_inbox_overlay(controller, monkeypatch)
        x, y = _button_center(overlay, staged["proposal_id"], "reject")
        revision = controller.content_revision

        handled = controller.handle_mouse_click(x, y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0)

        assert handled is True
        assert controller.proposal_inbox.list_pending() == []
        assert len(scene_controller.all_sprites) == 0
        assert scene_controller._loaded_scene_data["entities"] == []
        assert controller.undo.undo_stack == []
        assert controller.content_revision == revision
    finally:
        bridge.stop()


def test_ai_proposals_overlay_click_not_reached_from_other_right_tab(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _make_controller()
    bridge = EditorLiveSessionBridge(controller, tmp_path)
    bridge.start(write_discovery=True)
    try:
        staged = _stage_with_drain(controller, bridge, tmp_path, [_guard_add_op("wrong_tab_guard")])
        overlay = _install_and_draw_inbox_overlay(controller, monkeypatch)
        x, y = _button_center(overlay, staged["proposal_id"], "accept")
        controller.dock.set_right_tab("Inspector", force=True)
        calls: list[tuple[float, float, int, int]] = []

        def fail_if_called(px: float, py: float, button: int, modifiers: int = 0) -> bool:
            calls.append((px, py, button, modifiers))
            return True

        overlay.on_mouse_press = fail_if_called  # type: ignore[method-assign]

        handled = controller.handle_mouse_click(x, y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0)

        assert handled is True
        assert calls == []
        assert len(controller.proposal_inbox.list_pending()) == 1
    finally:
        bridge.stop()


def test_ai_proposals_overlay_renders_proposal_id_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _make_controller()
    bridge = EditorLiveSessionBridge(controller, tmp_path)
    bridge.start(write_discovery=True)
    drawn: list[str] = []
    try:
        staged = _stage_with_drain(controller, bridge, tmp_path, [_guard_add_op("id_line_guard")])
        _install_and_draw_inbox_overlay(controller, monkeypatch, text_sink=drawn)

        assert f"ID: {staged['proposal_id']}" in drawn
    finally:
        bridge.stop()


def test_ai_proposals_overlay_skips_id_line_when_proposal_id_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _make_controller()
    drawn: list[str] = []

    class InboxStub:
        def list_pending(self) -> list[dict[str, object]]:
            return [{"preview_summary": "Preview without id", "dry_run": {"ok": True}, "affected_ids": []}]

    controller.proposal_inbox = InboxStub()
    _install_and_draw_inbox_overlay(controller, monkeypatch, text_sink=drawn)

    assert not any(text.startswith("ID:") for text in drawn)


def test_ai_proposals_id_line_is_not_clickable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _make_controller()
    bridge = EditorLiveSessionBridge(controller, tmp_path)
    bridge.start(write_discovery=True)
    drawn: list[str] = []
    try:
        staged = _stage_with_drain(controller, bridge, tmp_path, [_guard_add_op("id_click_guard")])
        overlay = _install_and_draw_inbox_overlay(controller, monkeypatch, text_sink=drawn)
        id_line = f"ID: {staged['proposal_id']}"

        assert id_line in drawn
        assert set(overlay._button_rects) == {
            (staged["proposal_id"], "accept"),
            (staged["proposal_id"], "reject"),
        }
        assert overlay.on_mouse_press(640.0, 360.0, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is False
    finally:
        bridge.stop()


def test_ai_proposals_creator_door_accept_click_applies_through_official_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _make_controller()
    scene_controller = controller.window.scene_controller
    door = _install_creator_door_entity(controller)
    bridge = EditorLiveSessionBridge(controller, tmp_path)
    bridge.start(write_discovery=True)
    try:
        staged = _stage_creator_door_with_drain(controller, bridge, tmp_path)
        pending = controller.proposal_inbox.list_pending()
        assert pending[0]["dry_run"]["ok"] is True
        assert len(scene_controller.all_sprites) == 1
        assert door["behaviour_config"]["SceneExit"]["target_scene"] == "town"

        overlay = _install_and_draw_inbox_overlay(controller, monkeypatch)
        x, y = _button_center(overlay, staged["proposal_id"], "accept")

        handled = controller.handle_mouse_click(x, y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0)

        assert handled is True
        assert controller.proposal_inbox.list_pending() == []
        assert door["behaviour_config"]["SceneExit"]["target_scene"] == "dungeon"
        assert door["behaviour_config"]["SceneExit"]["target_spawn"] == "north_entry"
        assert len(controller.undo.undo_stack) == 1
        assert controller.undo.undo_stack[0]["type"] == "ApplyAIOpBatch"

        assert controller.undo.undo() is True
        assert door["behaviour_config"]["SceneExit"]["target_scene"] == "town"
        assert door["behaviour_config"]["SceneExit"]["target_spawn"] == "entry"
    finally:
        bridge.stop()


def test_ai_proposals_accept_hitbox_regression_with_id_line_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _make_controller()
    bridge = EditorLiveSessionBridge(controller, tmp_path)
    bridge.start(write_discovery=True)
    drawn: list[str] = []
    try:
        staged = _stage_with_drain(controller, bridge, tmp_path, [_guard_add_op("hitbox_guard")])
        overlay = _install_and_draw_inbox_overlay(controller, monkeypatch, text_sink=drawn)
        proposal_id = staged["proposal_id"]
        id_line = f"ID: {proposal_id}"

        assert id_line in drawn
        assert (proposal_id, "accept") in overlay._button_rects
        left, bottom, width, height = overlay._button_rects[(proposal_id, "accept")]
        center_x, center_y = _button_center(overlay, proposal_id, "accept")

        assert left <= center_x <= left + width
        assert bottom <= center_y <= bottom + height
        assert overlay.on_mouse_press(left - 1.0, center_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is False
        assert overlay.on_mouse_press(left + width + 1.0, center_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is False
        assert overlay.on_mouse_press(center_x, center_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
        assert controller.proposal_inbox.list_pending() == []
    finally:
        bridge.stop()


def test_ai_proposals_failed_dry_run_disables_accept_click(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _make_controller()
    scene_controller = controller.window.scene_controller
    door = _install_creator_door_entity(controller)
    bridge = EditorLiveSessionBridge(controller, tmp_path)
    bridge.start(write_discovery=True)
    try:
        staged = _stage_with_drain(
            controller,
            bridge,
            tmp_path,
            _creator_door_ops(scene_path="forest"),
        )
        pending = controller.proposal_inbox.list_pending()
        assert pending[0]["dry_run"]["ok"] is False

        overlay = _install_and_draw_inbox_overlay(controller, monkeypatch)
        assert (staged["proposal_id"], "accept") not in overlay._button_rects
        assert (staged["proposal_id"], "reject") in overlay._button_rects

        reject_x, reject_y = _button_center(overlay, staged["proposal_id"], "reject")
        assert controller.handle_mouse_click(reject_x, reject_y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True
        assert controller.proposal_inbox.list_pending() == []
        assert door["behaviour_config"]["SceneExit"]["target_scene"] == "town"
        assert controller.undo.undo_stack == []
        assert len(scene_controller.all_sprites) == 1
    finally:
        bridge.stop()


def test_ai_proposals_stale_accept_click_is_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _make_controller()
    scene_controller = controller.window.scene_controller
    bridge = EditorLiveSessionBridge(controller, tmp_path)
    bridge.start(write_discovery=True)
    try:
        staged = _stage_with_drain(controller, bridge, tmp_path, [_guard_add_op("stale_click_guard")])
        overlay = _install_and_draw_inbox_overlay(controller, monkeypatch)
        x, y = _button_center(overlay, staged["proposal_id"], "accept")

        from tests.test_cocreative_live_ops import _add_entity

        _add_entity(controller, "human_edit")
        revision = controller.content_revision
        sprite_count = len(scene_controller.all_sprites)
        entity_payload = list(scene_controller._loaded_scene_data["entities"])

        overlay.draw()
        x, y = _button_center(overlay, staged["proposal_id"], "accept")
        handled = controller.handle_mouse_click(x, y, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0)

        assert handled is True
        assert len(controller.proposal_inbox.list_pending()) == 1
        assert len(scene_controller.all_sprites) == sprite_count
        assert scene_controller._loaded_scene_data["entities"] == entity_payload
        assert controller.content_revision == revision
        assert "stale_click_guard" not in _entity_names(scene_controller.build_scene_snapshot(compact=False))
    finally:
        bridge.stop()


def _install_and_draw_inbox_overlay(
    controller: Any,
    monkeypatch: pytest.MonkeyPatch,
    *,
    text_sink: list[str] | None = None,
) -> ProposalInboxOverlay:
    import engine.ui_overlays.proposal_inbox_overlay as overlay_module

    monkeypatch.setattr(overlay_module, "_draw_tb_rectangle_filled", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(overlay_module, "_draw_tb_rectangle_outline", lambda *_args, **_kwargs: None)

    if text_sink is not None:
        def _capture(text: object, *_args, **_kwargs) -> None:
            text_sink.append(str(text))

        monkeypatch.setattr(overlay_module, "draw_text_cached", _capture)
    else:
        monkeypatch.setattr(overlay_module, "draw_text_cached", lambda *_args, **_kwargs: None)

    controller.window.editor_controller = controller
    overlay = ProposalInboxOverlay(controller.window)
    controller.window.proposal_inbox_overlay = overlay
    controller.dock.set_right_tab("AI Proposals", force=True)
    overlay.draw()
    return overlay


def _button_center(overlay: ProposalInboxOverlay, proposal_id: str, action: str) -> tuple[float, float]:
    rects = getattr(overlay, "_button_rects")
    left, bottom, width, height = rects[(proposal_id, action)]
    return left + (width / 2), bottom + (height / 2)
