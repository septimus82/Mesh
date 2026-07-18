"""Creator Mode selected-entity display-label rename proposal contracts."""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from engine.editor.creator_mode import (
    ENTITY_RENAME_DRAFT_ACTION_ID,
    ENTITY_RENAME_STAGE_ACTION_ID,
    CreatorModeController,
    build_creator_entity_rename_live_ops,
    build_creator_entity_rename_request,
    build_creator_overlay_model,
    validate_display_label,
)
from engine.editor.creator_mode.creator_entity_rename_request import (
    creator_entity_rename_request_key,
)
from engine.editor.creator_mode.creator_overlay_renderer import (
    build_creator_overlay_draw_commands,
    hit_test_creator_overlay_click,
)
from engine.editor.editor_command_dispatch_controller import EditorCommandDispatchController
from engine.editor.editor_live_ops_controller import EditorLiveOpsController

pytestmark = pytest.mark.fast


class FakeBridge:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, Any]]] = []
        self._pending: list[dict[str, Any]] = []
        self._counter = 0

    def stage_pending_proposal(self, ops: list[dict[str, Any]]) -> dict[str, Any]:
        self.calls.append(copy.deepcopy(ops))
        self._counter += 1
        proposal_id = f"rename-proposal-{self._counter}"
        proposal = {
            "proposal_id": proposal_id,
            "id": proposal_id,
            "preview_summary": f"Rename {ops[0].get('entity_id')} display label",
            "ops": copy.deepcopy(ops),
            "dry_run": {"ok": True, "warnings": [], "affected_ids": [str(ops[0].get("entity_id"))]},
        }
        self._pending.append(proposal)
        return {"ok": True, "proposal_id": proposal_id, "proposal": proposal}

    def list_pending_proposals(self) -> list[dict[str, Any]]:
        return list(self._pending)

    def clear(self) -> None:
        self._pending.clear()


class _Sprite:
    def __init__(self, data: dict[str, Any]) -> None:
        self.mesh_entity_data = data
        self.mesh_name = data.get("name", "")


def _crate(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": "crate_01",
        "name": "Crate",
        "x": 320.0,
        "y": 192.0,
        "behaviours": ["StaticSprite"],
    }
    data.update(overrides)
    return data


def _door() -> dict[str, Any]:
    return _crate(
        id="FieldDoor",
        name="Field Door",
        behaviours=["SceneTransition", "Interactable"],
        behaviour_config={
            "SceneTransition": {
                "target_scene": "scenes/door_interior.json",
                "spawn_id": "from_field",
            },
            "Interactable": {"event": "use"},
        },
    )


def _editor(
    selected: dict[str, Any] | None,
    *,
    bridge: Any = None,
    width: float = 1280.0,
    height: float = 720.0,
) -> SimpleNamespace:
    entity = _Sprite(selected) if selected is not None else None
    window = SimpleNamespace(
        width=width,
        height=height,
        scene_controller=SimpleNamespace(current_scene_path="scenes/door_field.json"),
    )
    return SimpleNamespace(
        selected_entity=entity,
        live_bridge=bridge if bridge is not None else FakeBridge(),
        grid_size=32.0,
        window=window,
        proposal_inbox=object(),
        dock=SimpleNamespace(
            right_tab="Inspector",
            get_right_collapsed=lambda: False,
            toggle_right_dock=lambda _e: None,
            apply_tab_change=lambda _e, _side, _tab: True,
            get_viewport_maximized=lambda: False,
            toggle_viewport_maximized=lambda _e: None,
        ),
    )


def _controller(
    selected: dict[str, Any] | None,
    *,
    bridge: Any = None,
    width: float = 1280.0,
    height: float = 720.0,
) -> CreatorModeController:
    controller = CreatorModeController(
        _editor(selected, bridge=bridge, width=width, height=height)
    )
    controller.show()
    return controller


def _commands(controller: CreatorModeController, width: float = 1280.0, height: float = 720.0):
    model = build_creator_overlay_model(controller.build_snapshot())
    return build_creator_overlay_draw_commands(model, width, height)


def test_authored_entity_with_stable_id_and_name_is_eligible_after_changed_draft() -> None:
    request = build_creator_entity_rename_request(
        _crate(),
        source_scene="scenes/door_field.json",
        proposed_label="Supply Crate",
    )
    assert request.ok is True
    assert request.entity_id == "crate_01"
    assert request.current_label == "Crate"
    assert request.proposed_label == "Supply Crate"


@pytest.mark.parametrize(
    ("selected", "reason"),
    [
        (None, "No entity"),
        ({"name": "Only Name"}, "stable authored identity"),
        ({"id": "runtime", "name": "Runtime", "_runtime_generated": True}, "authored scene"),
        ({"id": "missing"}, "editable display label"),
        ({"id": "bad", "name": "Bad\nLabel"}, "malformed"),
    ],
)
def test_rename_request_fails_closed_for_ineligible_selection(
    selected: dict[str, Any] | None,
    reason: str,
) -> None:
    request = build_creator_entity_rename_request(
        selected,
        source_scene="scenes/door_field.json",
        proposed_label="New Label",
    )
    assert request.ok is False
    assert reason in request.reason


def test_door_entity_with_stable_id_and_name_remains_eligible() -> None:
    request = build_creator_entity_rename_request(
        _door(),
        source_scene="scenes/door_field.json",
        proposed_label="Interior Entrance",
    )
    assert request.ok is True
    assert request.entity_id == "FieldDoor"


@pytest.mark.parametrize(
    ("proposed", "current", "expected"),
    [
        ("", "Crate", "Enter a display label."),
        ("   ", "Crate", "Enter a display label."),
        (" Crate ", "Crate", "matches the current"),
        ("Bad\nLabel", "Crate", "unsupported characters"),
        ("x" * 81, "Crate", "too long"),
        ("Ångström Label", "Crate", ""),
        ("Supply   Crate", "Crate", ""),
    ],
)
def test_display_label_validation(proposed: str, current: str, expected: str) -> None:
    reason = validate_display_label(proposed, current_label=current)
    assert expected in reason


def test_overlay_model_shows_stable_id_current_label_and_disabled_unchanged_action() -> None:
    controller = _controller(_crate())
    snapshot = controller.build_snapshot()
    panel = snapshot.rename_panel
    assert panel is not None
    assert panel.entity_id == "crate_01"
    assert panel.current_label == "Crate"
    assert panel.action.enabled is False
    assert "matches the current" in panel.action.reason
    text = "\n".join(command.text for command in _commands(controller))
    assert "Stable ID remains: crate_01" in text
    assert "Current label: Crate" in text


def test_valid_typed_draft_enables_stage_and_click_stages_proposal() -> None:
    bridge = FakeBridge()
    controller = _controller(_crate(), bridge=bridge)
    draft = next(c for c in _commands(controller) if c.action_id == ENTITY_RENAME_DRAFT_ACTION_ID)
    controller.handle_overlay_click(
        (draft.hit_left + draft.hit_right) / 2,
        (draft.hit_bottom + draft.hit_top) / 2,
    )
    assert controller.rename_text_focused is True
    for ch in " Box":
        assert controller.handle_key_input(ord(ch), 0) is True

    commands = _commands(controller)
    stage = next(c for c in commands if c.action_id == ENTITY_RENAME_STAGE_ACTION_ID)
    assert hit_test_creator_overlay_click(
        commands,
        (stage.hit_left + stage.hit_right) / 2,
        (stage.hit_bottom + stage.hit_top) / 2,
    ) == ENTITY_RENAME_STAGE_ACTION_ID
    result = controller.handle_overlay_click(
        (stage.hit_left + stage.hit_right) / 2,
        (stage.hit_bottom + stage.hit_top) / 2,
    )

    assert result is not None
    assert result.ok is True
    assert bridge.calls[0][0]["type"] == "set_entity_display_label"
    assert bridge.calls[0][0]["entity_id"] == "crate_01"
    assert bridge.calls[0][0]["expected_current_label"] == "Crate"
    assert bridge.calls[0][0]["label"] == "Crate Box"


def test_staging_does_not_mutate_selected_entity_or_dirty_revision() -> None:
    bridge = FakeBridge()
    entity = _crate()
    controller = _controller(entity, bridge=bridge)
    before = dict(entity)
    controller.build_snapshot()
    controller._rename_draft = "Supply Crate"
    result = controller.stage_selected_entity_rename()

    assert result.ok is True
    assert entity == before
    assert getattr(controller._editor, "content_revision", 0) == 0
    assert len(bridge.calls) == 1


def test_duplicate_rename_staging_blocks_until_pending_removed() -> None:
    bridge = FakeBridge()
    controller = _controller(_crate(), bridge=bridge)
    controller.build_snapshot()
    controller._rename_draft = "Supply Crate"
    first = controller.stage_selected_entity_rename()
    second = controller.stage_selected_entity_rename()
    assert first.ok is True
    assert second.ok is False
    assert "already staged" in second.errors[0]
    assert len(bridge.calls) == 1

    controller._rename_draft = "Supply Box"
    assert controller.stage_selected_entity_rename().ok is True
    bridge.clear()
    controller._prune_stale_rename_keys()
    controller._rename_draft = "Supply Crate"
    assert controller.stage_selected_entity_rename().ok is True


def test_changed_current_label_creates_new_duplicate_key() -> None:
    a = build_creator_entity_rename_request(
        _crate(name="Crate"),
        source_scene="scenes/door_field.json",
        proposed_label="Supply Crate",
    )
    b = build_creator_entity_rename_request(
        _crate(name="Box"),
        source_scene="scenes/door_field.json",
        proposed_label="Supply Crate",
    )
    assert creator_entity_rename_request_key(a) != creator_entity_rename_request_key(b)


@pytest.mark.parametrize(("width", "height"), [(1660, 895), (1280, 720), (1024, 600), (800, 600)])
def test_rename_layout_keeps_field_and_stage_reachable(width: int, height: int) -> None:
    controller = _controller(_door(), width=float(width), height=float(height))
    controller.build_snapshot()
    controller._rename_draft = "Interior Entrance"
    commands = _commands(controller, width=float(width), height=float(height))
    rename_cmds = [
        c for c in commands if c.action_id in {ENTITY_RENAME_DRAFT_ACTION_ID, ENTITY_RENAME_STAGE_ACTION_ID}
    ]
    assert {c.action_id for c in rename_cmds} == {
        ENTITY_RENAME_DRAFT_ACTION_ID,
        ENTITY_RENAME_STAGE_ACTION_ID,
    }
    for command in rename_cmds:
        assert command.region == "right"
        assert 0.0 <= command.hit_bottom <= command.hit_top <= float(height)
    assert len([c for c in commands if c.action_id == ENTITY_RENAME_STAGE_ACTION_ID]) == 1


def test_disabled_or_unavailable_stage_emits_no_stage_hitbox() -> None:
    controller = _controller(_crate())
    commands = _commands(controller)
    assert [c.action_id for c in commands].count(ENTITY_RENAME_STAGE_ACTION_ID) == 0
    assert [c.action_id for c in commands].count(ENTITY_RENAME_DRAFT_ACTION_ID) == 1


def test_focus_clears_on_selection_change_and_escape() -> None:
    controller = _controller(_crate())
    draft = next(c for c in _commands(controller) if c.action_id == ENTITY_RENAME_DRAFT_ACTION_ID)
    controller.handle_overlay_click((draft.hit_left + draft.hit_right) / 2, (draft.hit_bottom + draft.hit_top) / 2)
    assert controller.rename_text_focused is True
    controller._editor.selected_entity = _Sprite(_crate(id="crate_02", name="Other Crate"))
    assert controller.build_snapshot().rename_panel.current_label == "Other Crate"
    assert controller.rename_text_focused is False
    draft = next(c for c in _commands(controller) if c.action_id == ENTITY_RENAME_DRAFT_ACTION_ID)
    controller.handle_overlay_click((draft.hit_left + draft.hit_right) / 2, (draft.hit_bottom + draft.hit_top) / 2)
    assert controller.handle_key_input(optional_arcade.arcade.key.ESCAPE, 0) is True
    assert controller.rename_text_focused is False


def test_live_ops_preview_summary_and_payload_are_human_readable() -> None:
    request = build_creator_entity_rename_request(
        _crate(),
        source_scene="scenes/door_field.json",
        proposed_label="Supply Crate",
    )
    live = build_creator_entity_rename_live_ops(request)
    assert live.ok is True
    assert live.ops[0]["type"] == "set_entity_display_label"
    assert live.ops[0]["field"] == "name"
    assert "Rename crate_01 display label" in live.preview_summary


class _LiveEditor:
    def __init__(self, entity: dict[str, Any]) -> None:
        self.sprite = _Sprite(entity)
        self.content_revision = 0
        self.undo_stack: list[dict[str, Any]] = []
        self.redo_stack: list[dict[str, Any]] = []
        scene_controller = SimpleNamespace(
            current_scene_path="scenes/door_field.json",
            _loaded_scene_data={"entities": [self.sprite.mesh_entity_data]},
            all_sprites=[self.sprite],
            _ensure_entity_data_dict=lambda sprite: sprite.mesh_entity_data,
        )
        self.window = SimpleNamespace(scene_controller=scene_controller)
        self.selected_entity = self.sprite
        self.command_dispatch = EditorCommandDispatchController(self)
        self.live_ops = EditorLiveOpsController(self)
        self.refreshes: list[str] = []

    def _find_entity_by_id(self, entity_id: str) -> Any:
        data = self.sprite.mesh_entity_data
        if data.get("id") == entity_id or data.get("entity_id") == entity_id:
            return self.sprite
        return None

    def _find_entity_by_name(self, name: str) -> Any:
        return self.sprite if self.sprite.mesh_name == name else None

    def _push_command(self, command: dict[str, Any]) -> None:
        self.undo_stack.append(copy.deepcopy(command))
        self.redo_stack.clear()
        self.content_revision += 1

    def _refresh_hierarchy_list(self) -> None:
        self.refreshes.append("hierarchy")

    def _refresh_inspector_items(self) -> None:
        self.refreshes.append("inspector")

    def _refresh_entity_panels_list(self, *, sync_selected: bool = False) -> None:
        self.refreshes.append(f"entity_panels:{sync_selected}")

    def stage_proposal(self, ops: list[dict[str, Any]]) -> Any:
        return self.live_ops.stage_proposal(ops)

    def accept_proposal(self, proposal: Any) -> dict[str, Any]:
        return self.live_ops.accept_proposal(proposal)

    def reject_proposal(self, proposal: Any) -> dict[str, Any]:
        return self.live_ops.reject_proposal(proposal)


def test_accept_changes_only_display_label_and_pushes_one_undoable_batch() -> None:
    entity = _door()
    editor = _LiveEditor(entity)
    op = {
        "type": "set_entity_display_label",
        "scene_path": "scenes/door_field.json",
        "entity_id": "FieldDoor",
        "field": "name",
        "expected_current_label": "Field Door",
        "label": "Interior Entrance",
    }
    proposal = editor.stage_proposal([op])
    assert proposal.dry_run["ok"] is True
    before_config = copy.deepcopy(entity["behaviour_config"])

    result = editor.accept_proposal(proposal)

    assert result["ok"] is True
    assert entity["id"] == "FieldDoor"
    assert entity["name"] == "Interior Entrance"
    assert entity["behaviour_config"] == before_config
    assert editor.sprite.mesh_name == "Interior Entrance"
    assert len(editor.undo_stack) == 1
    child = editor.undo_stack[0]["children"][0]
    assert child["type"] == "SetEntityDisplayLabel"


def test_reject_leaves_label_and_stable_id_unchanged() -> None:
    entity = _crate()
    editor = _LiveEditor(entity)
    proposal = editor.stage_proposal(
        [
            {
                "type": "set_entity_display_label",
                "scene_path": "scenes/door_field.json",
                "entity_id": "crate_01",
                "field": "name",
                "expected_current_label": "Crate",
                "label": "Supply Crate",
            }
        ]
    )

    result = editor.reject_proposal(proposal)

    assert result["ok"] is True
    assert entity["id"] == "crate_01"
    assert entity["name"] == "Crate"
    assert editor.undo_stack == []


def test_stale_proposal_changed_current_label_fails_closed() -> None:
    entity = _crate()
    editor = _LiveEditor(entity)
    proposal = editor.stage_proposal(
        [
            {
                "type": "set_entity_display_label",
                "scene_path": "scenes/door_field.json",
                "entity_id": "crate_01",
                "field": "name",
                "expected_current_label": "Crate",
                "label": "Supply Crate",
            }
        ]
    )
    entity["name"] = "Changed Elsewhere"

    result = editor.accept_proposal(proposal)

    assert result["ok"] is False
    assert "changed" in result["message"]
    assert entity["name"] == "Changed Elsewhere"


def test_wrong_scene_and_missing_entity_fail_closed() -> None:
    editor = _LiveEditor(_crate())
    wrong_scene = editor.live_ops.apply_live_op(
        {
            "type": "set_entity_display_label",
            "scene_path": "other.json",
            "entity_id": "crate_01",
            "field": "name",
            "expected_current_label": "Crate",
            "label": "Supply Crate",
        }
    )
    missing = editor.live_ops.apply_live_op(
        {
            "type": "set_entity_display_label",
            "scene_path": "scenes/door_field.json",
            "entity_id": "missing",
            "field": "name",
            "expected_current_label": "Crate",
            "label": "Supply Crate",
        }
    )
    assert wrong_scene["ok"] is False
    assert missing["ok"] is False


def test_undo_and_redo_restore_labels_without_changing_stable_id() -> None:
    entity = _crate()
    editor = _LiveEditor(entity)
    command = {
        "type": "SetEntityDisplayLabel",
        "entity_id": "crate_01",
        "field": "name",
        "before": "Crate",
        "after": "Supply Crate",
    }

    editor.command_dispatch.apply_command(command)
    assert entity["name"] == "Supply Crate"
    assert entity["id"] == "crate_01"
    editor.command_dispatch.revert_command(command)
    assert entity["name"] == "Crate"
    assert entity["id"] == "crate_01"
