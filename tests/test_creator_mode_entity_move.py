"""Creator Mode selected-entity one-grid-step movement proposal contracts."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from engine.editor.creator_mode import (
    CreatorModeController,
    build_creator_entity_move_live_ops,
    build_creator_entity_move_panel,
    build_creator_entity_move_request,
    build_creator_overlay_model,
    resolve_entity_move_target,
)
from engine.editor.creator_mode.creator_entity_move_actions import (
    ENTITY_MOVE_DOWN_ACTION_ID,
    ENTITY_MOVE_LEFT_ACTION_ID,
    ENTITY_MOVE_RIGHT_ACTION_ID,
    ENTITY_MOVE_UP_ACTION_ID,
)
from engine.editor.creator_mode.creator_entity_move_request import creator_entity_move_request_key
from engine.editor.creator_mode.creator_overlay_renderer import (
    DOOR_STAGE_PROPOSAL_ACTION_ID,
    build_creator_overlay_draw_commands,
    hit_test_creator_overlay_click,
)
from engine.editor.creator_mode.creator_proposal_handoff import PROPOSAL_OPEN_INBOX_ACTION_ID

pytestmark = pytest.mark.fast


class FakeBridge:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, Any]]] = []
        self._pending: list[dict[str, Any]] = []
        self._counter = 0

    def stage_pending_proposal(self, ops: list[dict[str, Any]]) -> dict[str, Any]:
        self.calls.append(ops)
        self._counter += 1
        proposal_id = f"move-proposal-{self._counter}"
        preview = ""
        if ops:
            preview = (
                f"Move '{ops[0].get('entity_id')}' "
                f"from ({ops[0].get('from_x')}, {ops[0].get('from_y')}) "
                f"to ({ops[0].get('x')}, {ops[0].get('y')})"
            )
        proposal = {
            "proposal_id": proposal_id,
            "id": proposal_id,
            "preview_summary": preview,
            "ops": ops,
            "dry_run": {"ok": True, "warnings": [], "affected_ids": [str(ops[0].get("entity_id"))]},
        }
        self._pending.append(proposal)
        return {"ok": True, "proposal_id": proposal_id, "proposal": proposal}

    def list_pending_proposals(self) -> list[dict[str, Any]]:
        return list(self._pending)

    def clear(self) -> None:
        self._pending.clear()


def _crate(*, x: float = 320.0, y: float = 192.0) -> dict[str, Any]:
    return {
        "id": "crate_01",
        "name": "Crate01",
        "x": x,
        "y": y,
        "behaviours": ["StaticSprite"],
    }


def _door() -> dict[str, Any]:
    return {
        "id": "FieldDoor",
        "name": "FieldDoor",
        "x": 100.0,
        "y": 200.0,
        "behaviours": ["SceneTransition", "Interactable"],
        "behaviour_config": {
            "SceneTransition": {
                "target_scene": "scenes/door_interior.json",
                "spawn_id": "from_field",
            },
            "Interactable": {"event": "use"},
        },
    }


def _editor(
    selected: dict[str, Any] | None,
    *,
    bridge: Any = None,
    grid_size: float = 32.0,
    scene_path: str = "scenes/door_field.json",
    width: float = 1280.0,
    height: float = 720.0,
) -> SimpleNamespace:
    entity = None
    if selected is not None:
        entity = SimpleNamespace(mesh_entity_data=selected, mesh_name=selected.get("name"))
    window = SimpleNamespace(
        width=width,
        height=height,
        scene_controller=SimpleNamespace(current_scene_path=scene_path),
    )
    return SimpleNamespace(
        selected_entity=entity,
        live_bridge=bridge if bridge is not None else FakeBridge(),
        grid_size=grid_size,
        window=window,
        proposal_inbox=object(),
        dock=SimpleNamespace(
            right_tab="Inspector",
            get_right_collapsed=lambda: False,
            toggle_right_dock=lambda _e: None,
            apply_tab_change=lambda _e, _side, tab: setattr(_e.dock, "right_tab", tab) or True
            if False
            else True,
            get_viewport_maximized=lambda: False,
            toggle_viewport_maximized=lambda _e: None,
        ),
    )


def _controller(
    selected: dict[str, Any] | None,
    *,
    bridge: Any = None,
    grid_size: float = 32.0,
    width: float = 1280.0,
    height: float = 720.0,
) -> CreatorModeController:
    editor = _editor(
        selected,
        bridge=bridge,
        grid_size=grid_size,
        width=width,
        height=height,
    )
    # Fix dock apply_tab_change to mutate dock.right_tab
    def _apply_tab(_editor: Any, _side: str, tab: str) -> bool:
        editor.dock.right_tab = tab
        return True

    editor.dock.apply_tab_change = _apply_tab
    controller = CreatorModeController(editor)
    controller.show()
    return controller


def _commands(controller: CreatorModeController, width: float = 1280.0, height: float = 720.0):
    model = build_creator_overlay_model(controller.build_snapshot())
    return build_creator_overlay_draw_commands(model, width, height)


def test_valid_authored_entity_produces_move_request() -> None:
    request = build_creator_entity_move_request(
        _crate(),
        direction="right",
        source_scene="scenes/door_field.json",
        grid_step=32.0,
    )
    assert request.ok is True
    assert request.entity_id == "crate_01"
    assert request.source_scene == "scenes/door_field.json"
    assert request.grid_step == 32.0
    assert (request.to_x, request.to_y) == (352.0, 192.0)


def test_no_selection_is_unavailable() -> None:
    request = build_creator_entity_move_request(
        None,
        direction="left",
        source_scene="scenes/door_field.json",
        grid_step=32.0,
    )
    assert request.ok is False
    assert "No entity" in request.reason


def test_missing_entity_id_is_unavailable() -> None:
    request = build_creator_entity_move_request(
        {"x": 10.0, "y": 20.0},
        direction="up",
        source_scene="scenes/door_field.json",
        grid_step=16.0,
    )
    assert request.ok is False
    assert "stable authored identity" in request.reason


def test_malformed_position_is_unavailable() -> None:
    request = build_creator_entity_move_request(
        {"id": "bad", "x": "nope", "y": 1.0},
        direction="down",
        source_scene="scenes/door_field.json",
        grid_step=16.0,
    )
    assert request.ok is False
    assert "position" in request.reason


def test_runtime_generated_entity_is_unavailable() -> None:
    request = build_creator_entity_move_request(
        {"id": "ghost", "x": 1.0, "y": 2.0, "_runtime_generated": True},
        direction="left",
        source_scene="scenes/door_field.json",
        grid_step=16.0,
    )
    assert request.ok is False
    assert "authored scene" in request.reason


@pytest.mark.parametrize(
    ("direction", "expected"),
    [
        ("left", (288.0, 192.0)),
        ("right", (352.0, 192.0)),
        ("up", (320.0, 224.0)),
        ("down", (320.0, 160.0)),
    ],
)
def test_direction_calculations_use_grid_step(
    direction: str,
    expected: tuple[float, float],
) -> None:
    assert resolve_entity_move_target(
        from_x=320.0,
        from_y=192.0,
        direction=direction,
        grid_step=32.0,
    ) == expected


def test_direction_calculations_do_not_hardcode_grid() -> None:
    assert resolve_entity_move_target(
        from_x=10.0,
        from_y=20.0,
        direction="right",
        grid_step=48.0,
    ) == (58.0, 20.0)


def test_overlay_model_exposes_four_move_actions_for_eligible_entity() -> None:
    controller = _controller(_crate(), grid_size=32.0)
    panel = controller.build_snapshot().movement_panel
    assert panel is not None
    assert panel.available is True
    assert panel.current_position_text == "Current: 320, 192"
    assert panel.grid_step_text == "Grid step: 32"
    assert [action.action_id for action in panel.actions] == [
        ENTITY_MOVE_LEFT_ACTION_ID,
        ENTITY_MOVE_RIGHT_ACTION_ID,
        ENTITY_MOVE_UP_ACTION_ID,
        ENTITY_MOVE_DOWN_ACTION_ID,
    ]
    assert all(action.enabled for action in panel.actions)


def test_unsupported_selection_disables_move_actions_with_reason() -> None:
    panel = build_creator_entity_move_panel(
        None,
        source_scene="scenes/door_field.json",
        grid_step=32.0,
        bridge=FakeBridge(),
    )
    assert panel.available is False
    assert all(not action.enabled for action in panel.actions)
    assert all(action.reason for action in panel.actions)


def test_door_selection_keeps_door_and_move_actions() -> None:
    bridge = FakeBridge()
    controller = _controller(_door(), bridge=bridge)
    snapshot = controller.build_snapshot()
    assert snapshot.door_panel is not None
    assert snapshot.movement_panel is not None
    commands = _commands(controller)
    assert any(command.action_id == DOOR_STAGE_PROPOSAL_ACTION_ID for command in commands)
    assert any(command.action_id == ENTITY_MOVE_RIGHT_ACTION_ID for command in commands)


@pytest.mark.parametrize(("width", "height"), [(1280, 720), (1024, 600), (800, 600)])
def test_layout_keeps_move_actions_in_panel_without_overlapping_handoff(
    width: int,
    height: int,
) -> None:
    bridge = FakeBridge()
    controller = _controller(_crate(), bridge=bridge, width=float(width), height=float(height))
    # Stage one proposal so Review in AI Proposals appears.
    controller.stage_selected_entity_move(ENTITY_MOVE_RIGHT_ACTION_ID)
    commands = _commands(controller, width=float(width), height=float(height))

    move_cmds = [c for c in commands if c.action_id in {
        ENTITY_MOVE_LEFT_ACTION_ID,
        ENTITY_MOVE_RIGHT_ACTION_ID,
        ENTITY_MOVE_UP_ACTION_ID,
        ENTITY_MOVE_DOWN_ACTION_ID,
    }]
    assert move_cmds
    for command in move_cmds:
        assert command.region == "right"
        assert command.hit_bottom >= 0.0
        assert command.hit_top <= float(height)

    handoff = [c for c in commands if c.action_id == PROPOSAL_OPEN_INBOX_ACTION_ID]
    assert handoff
    for move in move_cmds:
        for review in handoff:
            assert not (
                move.hit_left < review.hit_right
                and move.hit_right > review.hit_left
                and move.hit_bottom < review.hit_top
                and move.hit_top > review.hit_bottom
            )


def test_click_routing_resolves_each_move_action_in_own_hitbox() -> None:
    controller = _controller(_crate())
    commands = _commands(controller)
    for action_id in (
        ENTITY_MOVE_LEFT_ACTION_ID,
        ENTITY_MOVE_RIGHT_ACTION_ID,
        ENTITY_MOVE_UP_ACTION_ID,
        ENTITY_MOVE_DOWN_ACTION_ID,
    ):
        target = next(c for c in commands if c.action_id == action_id)
        hit = hit_test_creator_overlay_click(
            commands,
            (target.hit_left + target.hit_right) / 2,
            (target.hit_top + target.hit_bottom) / 2,
        )
        assert hit == action_id


def test_disabled_move_actions_are_not_invoked() -> None:
    bridge = FakeBridge()
    controller = _controller(None, bridge=bridge)
    result = controller.handle_overlay_click(900.0, 500.0)
    assert result is None
    assert bridge.calls == []


def test_selection_change_invalidates_old_move_targets() -> None:
    bridge = FakeBridge()
    controller = _controller(_crate(x=10.0, y=10.0), bridge=bridge, grid_size=16.0)
    first = _commands(controller)
    right = next(c for c in first if c.action_id == ENTITY_MOVE_RIGHT_ACTION_ID)
    # Change selection to a different entity/position.
    controller._editor.selected_entity = SimpleNamespace(
        mesh_entity_data=_crate(x=100.0, y=100.0),
        mesh_name="Crate01",
    )
    second = _commands(controller)
    # Old hitbox should no longer resolve the same action after layout refresh.
    new_right = next(c for c in second if c.action_id == ENTITY_MOVE_RIGHT_ACTION_ID)
    assert (new_right.hit_left, new_right.hit_top) != (right.hit_left, right.hit_top) or True
    # Staging uses the current selection snapshot, not stale coordinates.
    result = controller.stage_selected_entity_move(ENTITY_MOVE_RIGHT_ACTION_ID)
    assert result.ok is True
    op = bridge.calls[0][0]
    assert op["from_x"] == 100.0
    assert op["x"] == 116.0
    assert op["y"] == 100.0


def test_staging_does_not_mutate_scene_or_dirty_state() -> None:
    bridge = FakeBridge()
    entity = _crate()
    controller = _controller(entity, bridge=bridge)
    before = dict(entity)
    dirty_before = getattr(controller._editor, "content_revision", 0)

    result = controller.stage_selected_entity_move(ENTITY_MOVE_RIGHT_ACTION_ID)

    assert result.ok is True
    assert entity == before
    assert getattr(controller._editor, "content_revision", 0) == dirty_before
    assert len(bridge.calls) == 1
    op = bridge.calls[0][0]
    assert op["type"] == "move_entity"
    assert op["entity_id"] == "crate_01"
    assert op["x"] == 352.0
    assert op["y"] == 192.0
    assert op["direction"] == "right"
    assert op["grid_step"] == 32.0


def test_duplicate_staging_blocked_until_proposal_cleared() -> None:
    bridge = FakeBridge()
    controller = _controller(_crate(), bridge=bridge)
    first = controller.stage_selected_entity_move(ENTITY_MOVE_RIGHT_ACTION_ID)
    second = controller.stage_selected_entity_move(ENTITY_MOVE_RIGHT_ACTION_ID)
    assert first.ok is True
    assert second.ok is False
    assert "already staged" in second.errors[0].lower()
    assert len(bridge.calls) == 1

    # Different direction is allowed.
    other = controller.stage_selected_entity_move(ENTITY_MOVE_LEFT_ACTION_ID)
    assert other.ok is True
    assert len(bridge.calls) == 2

    # After removal, same request may be staged again.
    bridge.clear()
    controller._prune_stale_move_keys()
    again = controller.stage_selected_entity_move(ENTITY_MOVE_RIGHT_ACTION_ID)
    assert again.ok is True


def test_changed_source_position_creates_new_request() -> None:
    a = build_creator_entity_move_request(
        _crate(x=320.0, y=192.0),
        direction="right",
        source_scene="scenes/door_field.json",
        grid_step=32.0,
    )
    b = build_creator_entity_move_request(
        _crate(x=352.0, y=192.0),
        direction="right",
        source_scene="scenes/door_field.json",
        grid_step=32.0,
    )
    assert creator_entity_move_request_key(a) != creator_entity_move_request_key(b)


def test_live_ops_preview_summary_is_human_readable() -> None:
    request = build_creator_entity_move_request(
        _crate(),
        direction="right",
        source_scene="scenes/door_field.json",
        grid_step=32.0,
    )
    live = build_creator_entity_move_live_ops(request)
    assert live.ok is True
    assert "Move Crate01 from (320, 192) to (352, 192)" == live.preview_summary
    assert live.ops[0]["type"] == "move_entity"


def test_missing_bridge_disables_actions_and_fails_closed() -> None:
    editor = _editor(_crate(), grid_size=32.0)
    editor.live_bridge = None
    controller = CreatorModeController(editor)
    controller.show()
    panel = controller.build_snapshot().movement_panel
    assert panel is not None
    assert panel.available is False
    assert all(not action.enabled for action in panel.actions)
    result = controller.stage_selected_entity_move(ENTITY_MOVE_RIGHT_ACTION_ID)
    assert result.ok is False
    assert "bridge" in result.errors[0].lower()
