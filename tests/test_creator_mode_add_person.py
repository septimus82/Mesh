"""Creator Mode "Add Person" (CREATOR-FIRST-STEPS PR C).

Drives a real headless editor through the overlay: click the line field, type,
click stage. The real live bridge stores the proposal; accepting it must be one
undo step that removes the person and their line together.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.editor.creator_mode.creator_add_person import (
    ADD_PERSON_LINE_ACTION_ID,
    ADD_PERSON_STAGE_ACTION_ID,
)
from engine.editor.creator_mode.creator_overlay import build_creator_overlay_model
from engine.editor.creator_mode.creator_overlay_renderer import build_creator_overlay_draw_commands
from engine.editor.live_session_bridge import EditorLiveSessionBridge
from engine.scene_runtime.persistence import build_scene_snapshot
from engine.schema_validation import validate
from tests._headless_editor import headless_editor

pytestmark = [pytest.mark.fast]


def _creator(window, tmp_path: Path):
    editor = window.editor_controller
    editor.live_bridge = EditorLiveSessionBridge(editor, tmp_path)  # in-process API; no HTTP server
    creator = editor.creator_mode
    if not creator.active:
        creator.toggle()
    return editor, creator


def _commands(window, creator):
    model = build_creator_overlay_model(creator.build_snapshot())
    return build_creator_overlay_draw_commands(model, window.width, window.height)


def _click(window, creator, action_id: str) -> None:
    target = next(c for c in _commands(window, creator) if c.action_id == action_id)
    creator.handle_overlay_click(target.hit_left + 2.0, (target.hit_top + target.hit_bottom) / 2.0)


def _type_line(window, creator, text: str) -> None:
    from engine import arcade_fallback

    _click(window, creator, ADD_PERSON_LINE_ACTION_ID)
    assert creator.person_line_focused
    for _ in range(len("Hello!")):  # clear the prefilled default
        creator.handle_key_input(arcade_fallback.key.BACKSPACE)
    for ch in text:
        creator.handle_text_input(ch)


def _people(scene_controller) -> list[dict]:
    # Live sprites carry the entity data the editor saves (see build_scene_snapshot).
    entities = [getattr(sprite, "mesh_entity_data", None) or {} for sprite in scene_controller.all_sprites]
    return [e for e in entities if str(e.get("name", "")).startswith("Person")]


@pytest.fixture
def starter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    with headless_editor(tmp_path, monkeypatch) as window:
        yield window


def test_add_person_stages_exactly_the_add_and_dialogue_ops(starter, tmp_path: Path) -> None:
    editor, creator = _creator(starter, tmp_path)
    _type_line(starter, creator, "hi there")
    _click(starter, creator, ADD_PERSON_STAGE_ACTION_ID)

    pending = editor.live_bridge.list_pending_proposals()
    assert len(pending) == 1 and pending[0]["dry_run"]["ok"] is True
    ops = editor.live_bridge._proposals[pending[0]["proposal_id"]].ops
    assert [op["type"] for op in ops] == ["add_entity_from_prefab", "set_behaviour_params"]
    assert ops[0]["prefab_id"] == "person" and ops[0]["name"] == "Person"
    assert ops[0]["id"].startswith("start_person_")  # stable id, so Move/Rename can target it
    assert ops[1]["entity_name"] == "Person" and ops[1]["behaviour_name"] == "Dialogue"
    assert ops[1]["params"]["dialogue"]["nodes"]["root"]["text"] == "hi there"
    grid = float(editor.grid_size or 0) or 1.0
    assert ops[0]["x"] % grid == 0 and ops[0]["y"] % grid == 0
    # Staging never applies: nothing changed in the live scene yet.
    assert _people(starter.scene_controller) == []


def test_accept_is_one_undo_step_and_undo_removes_person_and_line(starter, tmp_path: Path) -> None:
    editor, creator = _creator(starter, tmp_path)
    _type_line(starter, creator, "hi there")
    _click(starter, creator, ADD_PERSON_STAGE_ACTION_ID)
    proposal_id = editor.live_bridge.list_pending_proposals()[0]["proposal_id"]
    undo_before = len(editor.undo.undo_stack)

    result = editor.live_bridge.accept_pending_proposal(proposal_id)
    assert result["ok"] is True, result
    assert len(editor.undo.undo_stack) == undo_before + 1
    (person,) = _people(starter.scene_controller)
    assert person["behaviour_config"]["Dialogue"]["dialogue"]["nodes"]["root"]["text"] == "hi there"
    assert person["id"].startswith("start_person_")
    # The running Dialogue behaviour must say the new line in this same session (F4 playtest),
    # not the prefab's "Hello!" it was created with.
    sprite = next(s for s in starter.scene_controller.all_sprites if (s.mesh_entity_data or {}).get("name") == "Person")
    dialogue = next(b for b in sprite.mesh_behaviours_runtime if type(b).__name__ == "Dialogue")
    assert dialogue._graph_nodes["root"]["text"] == "hi there"

    editor.undo_last()
    assert _people(starter.scene_controller) == []
    assert not any(e.get("name") == "Person" for e in starter.scene_controller._loaded_scene_data["entities"])


def test_added_person_can_be_repositioned_with_the_move_proposal(starter, tmp_path: Path) -> None:
    editor, creator = _creator(starter, tmp_path)
    _click(starter, creator, ADD_PERSON_STAGE_ACTION_ID)
    editor.live_bridge.accept_pending_proposal(editor.live_bridge.list_pending_proposals()[0]["proposal_id"])

    editor.selected_entity = next(
        s for s in starter.scene_controller.all_sprites if (getattr(s, "mesh_entity_data", None) or {}).get("name") == "Person"
    )
    movement = creator.build_snapshot().movement_panel
    assert movement is not None and movement.available, getattr(movement, "reason", movement)


def test_saved_scene_with_added_person_passes_roundtrip_contract(starter, tmp_path: Path) -> None:
    editor, creator = _creator(starter, tmp_path)
    _type_line(starter, creator, "hi there")
    _click(starter, creator, ADD_PERSON_STAGE_ACTION_ID)
    editor.live_bridge.accept_pending_proposal(editor.live_bridge.list_pending_proposals()[0]["proposal_id"])

    snapshot = build_scene_snapshot(starter.scene_controller)
    validate(snapshot, "scene.schema.json", "starter_with_person.json")
    saved = next(e for e in snapshot["entities"] if e.get("name") == "Person")
    assert saved["behaviour_config"]["Dialogue"]["dialogue"]["nodes"]["root"]["text"] == "hi there"
    # Without a saved stable id the person is unaddressable after the next reload.
    assert str(saved.get("id") or "").startswith("start_person_")


def test_second_add_is_blocked_while_the_first_is_pending(starter, tmp_path: Path) -> None:
    editor, creator = _creator(starter, tmp_path)
    _click(starter, creator, ADD_PERSON_STAGE_ACTION_ID)
    panel = creator.build_snapshot().add_person_panel
    assert panel.enabled is False and panel.reason == "Waiting for review in AI Proposals."
    assert not any(c.action_id == ADD_PERSON_STAGE_ACTION_ID for c in _commands(starter, creator))


def test_failing_dry_run_is_refused_and_leaves_no_pending_proposal(starter, tmp_path: Path) -> None:
    from engine.editor.creator_mode.creator_add_person import build_add_person_ops, stage_add_person_proposal

    editor, _ = _creator(starter, tmp_path)
    ops = build_add_person_ops(
        scene_path=starter.scene_controller.current_scene_path,
        entities=starter.scene_controller._loaded_scene_data["entities"],
        x=96.0,
        y=224.0,
        line="hi",
    )
    ops[0]["prefab_id"] = "no_such_prefab"  # the bridge stages it anyway; its dry-run fails

    result = stage_add_person_proposal(ops, editor.live_bridge)

    assert result.ok is False and "not found" in result.errors[0]
    assert editor.live_bridge.list_pending_proposals() == []


def test_second_project_in_same_process_does_not_inherit_prefabs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A starter project (has a person prefab) opened first must not leak into an empty-prefab project.
    with headless_editor(tmp_path / "first", monkeypatch, template_id="starter") as first:
        assert [entry["id"] for entry in first.editor_controller.prefab_palette] == ["person"]
    with headless_editor(tmp_path / "second", monkeypatch, template_id="blank") as second:
        editor, creator = _creator(second, tmp_path / "second")
        assert editor.prefab_palette == []
        panel = creator.build_snapshot().add_person_panel
        assert panel.enabled is False and panel.reason == "This project has no person prefab."


def test_project_without_person_prefab_disables_add_with_reason(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    with headless_editor(tmp_path, monkeypatch, template_id="blank") as window:
        editor, creator = _creator(window, tmp_path)
        panel = creator.build_snapshot().add_person_panel
        assert panel.enabled is False
        assert panel.reason == "This project has no person prefab."
        commands = _commands(window, creator)
        assert not any(c.action_id == ADD_PERSON_STAGE_ACTION_ID for c in commands)
        assert "no person prefab" in " ".join(c.text for c in commands)  # reason wraps in the left column
        assert creator.stage_add_person().ok is False
        assert editor.live_bridge.list_pending_proposals() == []
