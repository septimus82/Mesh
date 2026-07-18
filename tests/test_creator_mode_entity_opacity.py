"""Creator Mode selected-entity opacity proposal contracts."""

from __future__ import annotations

import copy
from types import SimpleNamespace
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from engine.editor.creator_mode import (
    ENTITY_OPACITY_DRAFT_ACTION_ID,
    ENTITY_OPACITY_STAGE_ACTION_ID,
    CreatorModeController,
    alpha_to_draft_percent,
    build_creator_entity_opacity_live_ops,
    build_creator_entity_opacity_request,
    build_creator_overlay_model,
    normalize_alpha,
    parse_opacity_percent_draft,
    resolve_alpha_state,
    validate_opacity_draft,
)
from engine.editor.creator_mode.creator_entity_opacity_panel import (
    ENTITY_OPACITY_PRESET_ACTION_PREFIX,
)
from engine.editor.creator_mode.creator_entity_opacity_request import (
    creator_entity_opacity_request_key,
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
        proposal_id = f"opacity-proposal-{self._counter}"
        proposal = {
            "proposal_id": proposal_id,
            "id": proposal_id,
            "preview_summary": f"Change {ops[0].get('entity_id')} opacity",
            "ops": copy.deepcopy(ops),
            "dry_run": {
                "ok": True,
                "warnings": [],
                "affected_ids": [str(ops[0].get("entity_id"))],
            },
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
        self.alpha = int(round(float(data.get("alpha", 1.0)) * 255.0))


def _crate(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": "crate_01",
        "name": "Crate",
        "x": 320.0,
        "y": 192.0,
        "solid": True,
        "behaviours": ["StaticSprite"],
    }
    data.update(overrides)
    return data


def _door(**overrides: Any) -> dict[str, Any]:
    data = _crate(
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
    data.update(overrides)
    return data


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


def test_alpha_semantics_use_authored_alpha_field_with_default_omission() -> None:
    omitted = resolve_alpha_state(_crate())
    explicit = resolve_alpha_state(_crate(alpha=1))
    zero = resolve_alpha_state(_crate(alpha=0.0))

    assert omitted is not None
    assert omitted.present is False
    assert omitted.effective_value == 1.0
    assert explicit is not None
    assert explicit.present is True
    assert explicit.authored_value == 1.0
    assert zero is not None
    assert zero.effective_value == 0.0


@pytest.mark.parametrize("value", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_alpha_range_accepts_zero_intermediate_and_one(value: float) -> None:
    assert normalize_alpha(value) == value


@pytest.mark.parametrize("value", [-0.01, 1.01, float("nan"), float("inf"), "bad", True])
def test_alpha_range_rejects_malformed_values(value: object) -> None:
    assert normalize_alpha(value) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [("0", 0.0), ("25", 0.25), ("50%", 0.5), ("75", 0.75), ("100", 1.0)],
)
def test_percent_conversion_is_canonical(text: str, expected: float) -> None:
    assert parse_opacity_percent_draft(text) == (expected, "")
    assert alpha_to_draft_percent(expected) == text.rstrip("%")


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("", "Enter an opacity"),
        ("nope", "Enter an opacity"),
        ("-1", "below 0%"),
        ("101", "exceed 100%"),
        ("100", "matches the current"),
    ],
)
def test_opacity_validation_rejects_invalid_and_unchanged(text: str, message: str) -> None:
    assert message in validate_opacity_draft(text, current_alpha=1.0)


@pytest.mark.parametrize(
    ("selected", "reason"),
    [
        (None, "Select one"),
        ({"name": "Only Name"}, "stable authored ID"),
        ({"id": "runtime", "name": "Runtime", "_runtime_generated": True}, "authored scene"),
        ({"id": "bad", "name": "Bad", "alpha": "opaque"}, "malformed"),
    ],
)
def test_opacity_request_fails_closed_for_ineligible_selection(
    selected: dict[str, Any] | None,
    reason: str,
) -> None:
    request = build_creator_entity_opacity_request(
        selected,
        source_scene="scenes/door_field.json",
        draft_percent="50",
    )
    assert request.ok is False
    assert reason in request.reason


def test_entity_id_fallback_is_supported_but_name_only_is_not() -> None:
    request = build_creator_entity_opacity_request(
        {"entity_id": "entity-2", "name": "Entity Two"},
        source_scene="scenes/door_field.json",
        draft_percent="50",
    )
    assert request.ok is True
    assert request.entity_id == "entity-2"

    name_only = build_creator_entity_opacity_request(
        {"name": "Entity Two"},
        source_scene="scenes/door_field.json",
        draft_percent="50",
    )
    assert name_only.ok is False


def test_overlay_model_shows_opacity_context_and_disabled_unchanged_action() -> None:
    controller = _controller(_crate())
    snapshot = controller.build_snapshot()
    panel = snapshot.opacity_panel
    assert panel is not None
    assert panel.entity_id == "crate_01"
    assert panel.current_percent == "Current: 100%"
    assert panel.draft_percent == "100"
    assert panel.action.enabled is False
    assert "matches the current" in panel.action.reason
    text = "\n".join(command.text for command in _commands(controller))
    assert "Opacity" in text
    assert "Stable ID: crate_01" in text
    assert "Current: 100%" in text


def test_typing_and_preset_update_only_draft_and_click_stages_proposal() -> None:
    bridge = FakeBridge()
    entity = _crate()
    controller = _controller(entity, bridge=bridge)
    draft = next(c for c in _commands(controller) if c.action_id == ENTITY_OPACITY_DRAFT_ACTION_ID)
    assert controller.handle_overlay_click(
        (draft.hit_left + draft.hit_right) / 2,
        (draft.hit_bottom + draft.hit_top) / 2,
    ) is not None
    assert controller.opacity_text_focused is True
    assert controller.handle_key_input(optional_arcade.arcade.key.DELETE, 0) is True
    for ch in "50":
        assert controller.handle_key_input(ord(ch), 0) is True

    commands = _commands(controller)
    stage = next(c for c in commands if c.action_id == ENTITY_OPACITY_STAGE_ACTION_ID)
    assert hit_test_creator_overlay_click(
        commands,
        (stage.hit_left + stage.hit_right) / 2,
        (stage.hit_bottom + stage.hit_top) / 2,
    ) == ENTITY_OPACITY_STAGE_ACTION_ID
    result = controller.handle_overlay_click(
        (stage.hit_left + stage.hit_right) / 2,
        (stage.hit_bottom + stage.hit_top) / 2,
    )

    assert result is not None
    assert result.ok is True
    assert bridge.calls[0][0]["type"] == "set_entity_alpha"
    assert bridge.calls[0][0]["field"] == "alpha"
    assert bridge.calls[0][0]["entity_id"] == "crate_01"
    assert bridge.calls[0][0]["expected_current_alpha"] == {"present": False, "effective": 1.0}
    assert bridge.calls[0][0]["alpha"] == 0.5
    assert "alpha" not in entity


def test_opacity_preset_has_own_hitbox_and_updates_draft_without_mutating_scene() -> None:
    entity = _crate()
    controller = _controller(entity)
    commands = _commands(controller)
    preset = next(c for c in commands if c.action_id == f"{ENTITY_OPACITY_PRESET_ACTION_PREFIX}25")
    result = controller.handle_overlay_click(
        (preset.hit_left + preset.hit_right) / 2,
        (preset.hit_bottom + preset.hit_top) / 2,
    )
    assert result is not None
    assert controller.build_snapshot().opacity_panel.draft_percent == "25"
    assert "alpha" not in entity


@pytest.mark.parametrize(("width", "height"), [(1660, 895), (1280, 720), (1024, 600), (800, 600)])
def test_opacity_layout_keeps_controls_reachable(width: int, height: int) -> None:
    controller = _controller(_door(), width=float(width), height=float(height))
    controller.build_snapshot()
    controller._opacity_draft = "50"
    commands = _commands(controller, width=float(width), height=float(height))
    opacity_cmds = [
        c for c in commands if c.action_id in {ENTITY_OPACITY_DRAFT_ACTION_ID, ENTITY_OPACITY_STAGE_ACTION_ID}
    ]
    assert {c.action_id for c in opacity_cmds} == {
        ENTITY_OPACITY_DRAFT_ACTION_ID,
        ENTITY_OPACITY_STAGE_ACTION_ID,
    }
    for command in opacity_cmds:
        assert command.region == "right"
        assert 0.0 <= command.hit_bottom <= command.hit_top <= float(height)
    assert len([c for c in commands if c.action_id == ENTITY_OPACITY_STAGE_ACTION_ID]) == 1


def test_duplicate_opacity_staging_blocks_until_pending_removed() -> None:
    bridge = FakeBridge()
    controller = _controller(_crate(), bridge=bridge)
    controller.build_snapshot()
    controller._opacity_draft = "50"
    first = controller.stage_selected_entity_opacity()
    second = controller.stage_selected_entity_opacity()
    assert first.ok is True
    assert second.ok is False
    assert "already staged" in second.errors[0]
    assert len(bridge.calls) == 1

    controller._opacity_draft = "25"
    assert controller.stage_selected_entity_opacity().ok is True
    bridge.clear()
    controller._prune_stale_opacity_keys()
    controller._opacity_draft = "50"
    assert controller.stage_selected_entity_opacity().ok is True


def test_changed_current_alpha_creates_new_duplicate_key() -> None:
    a = build_creator_entity_opacity_request(
        _crate(alpha=1.0),
        source_scene="scenes/door_field.json",
        draft_percent="50",
    )
    b = build_creator_entity_opacity_request(
        _crate(alpha=0.75),
        source_scene="scenes/door_field.json",
        draft_percent="50",
    )
    assert creator_entity_opacity_request_key(a) != creator_entity_opacity_request_key(b)


def test_live_ops_preview_summary_and_payload_are_narrow() -> None:
    request = build_creator_entity_opacity_request(
        _crate(),
        source_scene="scenes/door_field.json",
        draft_percent="25",
    )
    live = build_creator_entity_opacity_live_ops(request)
    assert live.ok is True
    assert live.ops[0]["type"] == "set_entity_alpha"
    assert live.ops[0]["field"] == "alpha"
    assert live.ops[0]["alpha"] == 0.25
    assert "Change crate_01 opacity from 100% to 25%" in live.preview_summary


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


def test_accept_changes_only_alpha_and_pushes_one_undoable_batch() -> None:
    entity = _door()
    editor = _LiveEditor(entity)
    op = {
        "type": "set_entity_alpha",
        "scene_path": "scenes/door_field.json",
        "entity_id": "FieldDoor",
        "field": "alpha",
        "expected_current_alpha": {"present": False, "effective": 1.0},
        "alpha": 0.5,
    }
    before = copy.deepcopy(entity)
    proposal = editor.stage_proposal([op])
    assert proposal.dry_run["ok"] is True

    result = editor.accept_proposal(proposal)

    assert result["ok"] is True
    assert entity["alpha"] == 0.5
    assert editor.sprite.alpha == 128
    for key in ("id", "name", "x", "y", "solid", "behaviour_config"):
        assert entity[key] == before[key]
    assert len(editor.undo_stack) == 1
    child = editor.undo_stack[0]["children"][0]
    assert child["type"] == "SetEntityAlpha"
    assert child["before"] == {"present": False, "effective": 1.0}


def test_reject_leaves_alpha_and_authored_representation_unchanged() -> None:
    entity = _crate(alpha=1.0)
    editor = _LiveEditor(entity)
    proposal = editor.stage_proposal(
        [
            {
                "type": "set_entity_alpha",
                "scene_path": "scenes/door_field.json",
                "entity_id": "crate_01",
                "field": "alpha",
                "expected_current_alpha": {"present": True, "value": 1.0, "effective": 1.0},
                "alpha": 0.25,
            }
        ]
    )

    result = editor.reject_proposal(proposal)

    assert result["ok"] is True
    assert entity["alpha"] == 1.0
    assert editor.undo_stack == []


def test_stale_proposal_changed_current_alpha_fails_closed() -> None:
    entity = _crate()
    editor = _LiveEditor(entity)
    proposal = editor.stage_proposal(
        [
            {
                "type": "set_entity_alpha",
                "scene_path": "scenes/door_field.json",
                "entity_id": "crate_01",
                "field": "alpha",
                "expected_current_alpha": {"present": False, "effective": 1.0},
                "alpha": 0.5,
            }
        ]
    )
    entity["alpha"] = 0.75

    result = editor.accept_proposal(proposal)

    assert result["ok"] is False
    assert "changed" in result["message"]
    assert entity["alpha"] == 0.75


def test_wrong_scene_missing_entity_and_arbitrary_property_paths_fail_closed() -> None:
    editor = _LiveEditor(_crate())
    base = {
        "type": "set_entity_alpha",
        "scene_path": "scenes/door_field.json",
        "entity_id": "crate_01",
        "field": "alpha",
        "expected_current_alpha": {"present": False, "effective": 1.0},
        "alpha": 0.5,
    }
    wrong_scene = editor.live_ops.apply_live_op({**base, "scene_path": "other.json"})
    missing = editor.live_ops.apply_live_op({**base, "entity_id": "missing"})
    arbitrary = editor.live_ops.apply_live_op({**base, "field": "solid"})
    assert wrong_scene["ok"] is False
    assert missing["ok"] is False
    assert arbitrary["ok"] is False


def test_undo_and_redo_restore_exact_alpha_representation_without_identity_churn() -> None:
    entity = _crate()
    editor = _LiveEditor(entity)
    command = {
        "type": "SetEntityAlpha",
        "entity_id": "crate_01",
        "field": "alpha",
        "before": {"present": False, "effective": 1.0},
        "after": {"present": True, "value": 0.0, "effective": 0.0},
    }

    editor.command_dispatch.apply_command(command)
    assert entity["alpha"] == 0.0
    assert entity["id"] == "crate_01"
    assert editor.sprite.alpha == 0
    editor.command_dispatch.revert_command(command)
    assert "alpha" not in entity
    assert entity["id"] == "crate_01"
    assert editor.sprite.alpha == 255


def test_zero_alpha_entity_remains_in_scene_data_and_selectable_route() -> None:
    entity = _crate(alpha=0.0)
    editor = _LiveEditor(entity)
    assert editor.window.scene_controller._loaded_scene_data["entities"] == [entity]
    assert list(editor.window.scene_controller.all_sprites) == [editor.sprite]
    assert editor._find_entity_by_id("crate_01") is editor.sprite
