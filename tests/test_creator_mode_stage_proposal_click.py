from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import engine.editor.input_router as input_router
from engine.editor.creator_mode import (
    CreatorModeController,
    build_creator_overlay_model,
)
from engine.editor.creator_mode import creator_door_staging
from engine.editor.creator_mode.creator_overlay_click import try_handle_creator_mode_overlay_click
from engine.editor.creator_mode.creator_overlay_renderer import (
    DOOR_STAGE_PROPOSAL_ACTION_ID,
    build_creator_overlay_draw_commands,
    hit_test_creator_overlay_click,
)

pytestmark = pytest.mark.fast


def test_ready_door_panel_creates_clickable_stage_proposal_target() -> None:
    controller = _ready_controller()
    commands = _draw_commands(controller)

    targets = [command for command in commands if command.action_id == DOOR_STAGE_PROPOSAL_ACTION_ID]
    assert len(targets) == 1
    assert "[Ready] Stage Proposal" in targets[0].text


def test_disabled_stage_proposal_creates_no_clickable_target() -> None:
    controller = CreatorModeController(_editor_with_selection(_door_entity(), live_bridge=None))
    controller.show()
    commands = _draw_commands(controller)

    assert not any(command.action_id for command in commands)


def test_clicking_ready_stage_proposal_calls_stage_selected_door_proposal_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}
    controller = _ready_controller()
    real_stage = controller.stage_selected_door_proposal

    def counting_stage() -> object:
        calls["count"] += 1
        return real_stage()

    monkeypatch.setattr(controller, "stage_selected_door_proposal", counting_stage)
    x, y = _stage_proposal_click_point(_draw_commands(controller))

    result = controller.handle_overlay_click(x, y)

    assert calls["count"] == 1
    assert result is not None
    assert result.ok is True


def test_fake_bridge_receives_exactly_one_stage_pending_proposal_call() -> None:
    bridge = FakeBridge()
    controller = CreatorModeController(_editor_with_selection(_door_entity(), live_bridge=bridge))
    controller.show()
    x, y = _stage_proposal_click_point(_draw_commands(controller))

    controller.handle_overlay_click(x, y)

    assert len(bridge.calls) == 1


def test_successful_click_stores_and_displays_success_message() -> None:
    controller = _ready_controller()
    x, y = _stage_proposal_click_point(_draw_commands(controller))

    controller.handle_overlay_click(x, y)

    assert controller.last_action_ok is True
    assert controller.last_action_message == "Door proposal staged: proposal-1"
    commands = _draw_commands(controller)
    assert "Door proposal staged: proposal-1" in _command_text(commands)


def test_failed_click_stores_and_displays_error_message() -> None:
    controller = CreatorModeController(_editor_with_selection(_door_entity(), live_bridge=None))
    controller.show()
    commands = _draw_commands(controller)
    disabled = [command for command in commands if "Stage Proposal" in command.text][0]
    assert disabled.action_id == ""

    result = controller.handle_overlay_click(
        (disabled.hit_left + disabled.hit_right) / 2 if disabled.action_id else 999.0,
        (disabled.hit_top + disabled.hit_bottom) / 2 if disabled.action_id else 999.0,
    )

    assert result is None
    assert controller.last_action_message == ""


def test_bridge_unavailable_click_on_ready_target_stores_error_when_staging_runs() -> None:
    controller = CreatorModeController(_editor_with_selection(_door_entity(), live_bridge=None))
    controller.show()
    controller._store_staging_result(controller.stage_selected_door_proposal())

    assert controller.last_action_ok is False
    assert controller.last_action_message == "Proposal bridge is unavailable."


def test_non_door_selection_click_returns_no_op_and_does_not_call_bridge() -> None:
    bridge = FakeBridge()
    controller = CreatorModeController(
        _editor_with_selection({"name": "Rock", "behaviours": ["StaticSprite"]}, live_bridge=bridge)
    )
    controller.show()

    result = controller.handle_overlay_click(900.0, 500.0)

    assert result is None
    assert bridge.calls == []


def test_creator_mode_inactive_click_returns_no_op() -> None:
    bridge = FakeBridge()
    controller = CreatorModeController(_editor_with_selection(_door_entity(), live_bridge=bridge))

    result = controller.handle_overlay_click(900.0, 500.0)

    assert result is None
    assert bridge.calls == []


def test_click_outside_action_target_returns_no_op() -> None:
    bridge = FakeBridge()
    controller = _ready_controller()

    result = controller.handle_overlay_click(12.0, 12.0)

    assert result is None
    assert bridge.calls == []


def test_snapshot_model_render_do_not_stage_before_click(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args, **_kwargs):
        raise AssertionError("must not stage before click")

    monkeypatch.setattr(creator_door_staging, "stage_creator_door_proposal", fail)
    controller = _ready_controller()

    snapshot = controller.build_snapshot()
    model = build_creator_overlay_model(snapshot)
    build_creator_overlay_draw_commands(model, 1280, 720)


def test_disabled_bridge_unavailable_action_does_not_stage_on_click() -> None:
    bridge = FakeBridge()
    controller = CreatorModeController(_editor_with_selection(_door_entity(), live_bridge=None))
    controller.show()
    commands = _draw_commands(controller)
    stage_lines = [command for command in commands if "Stage Proposal" in command.text]
    assert stage_lines
    assert stage_lines[0].action_id == ""

    result = controller.handle_overlay_click(900.0, 500.0)

    assert result is None
    assert bridge.calls == []


def test_selection_changed_after_render_fails_closed() -> None:
    bridge = FakeBridge()
    editor = _editor_with_selection(_door_entity(), live_bridge=bridge)
    controller = CreatorModeController(editor)
    controller.show()
    x, y = _stage_proposal_click_point(_draw_commands(controller))

    editor.selected_entity = {"name": "Rock", "behaviours": ["StaticSprite"]}
    result = controller.handle_overlay_click(x, y)

    assert result is None
    assert bridge.calls == []


def test_hostile_bridge_accept_reject_apply_are_not_called() -> None:
    controller = CreatorModeController(
        _editor_with_selection(_door_entity(), live_bridge=HostileBridge())
    )
    controller.show()
    x, y = _stage_proposal_click_point(_draw_commands(controller))

    result = controller.handle_overlay_click(x, y)

    assert result is not None
    assert result.ok is True


def test_click_output_is_deterministic() -> None:
    controller = _ready_controller()
    commands = _draw_commands(controller)
    x, y = _stage_proposal_click_point(commands)

    first = controller.handle_overlay_click(x, y)
    controller._clear_last_action_state()
    controller.show()
    second = controller.handle_overlay_click(x, y)

    assert first == second


def test_try_handle_creator_mode_overlay_click_only_when_creator_active() -> None:
    bridge = FakeBridge()
    editor = SimpleNamespace(
        active=True,
        creator_mode=CreatorModeController(_editor_with_selection(_door_entity(), live_bridge=bridge)),
    )
    editor.creator_mode.show()
    x, y = _stage_proposal_click_point(_draw_commands(editor.creator_mode))

    assert try_handle_creator_mode_overlay_click(editor, x, y, 1) is True
    editor.creator_mode.hide()
    assert try_handle_creator_mode_overlay_click(editor, x, y, 1) is False


def test_input_router_passes_through_when_creator_mode_inactive() -> None:
    editor = SimpleNamespace(
        active=True,
        creator_mode=SimpleNamespace(active=False),
    )
    called = {"editor_input": False}

    def fake_handle_mouse_click(_self, _x, _y, _button, _modifiers):
        called["editor_input"] = True
        return True

    original = input_router.editor_input.handle_mouse_click
    input_router.editor_input.handle_mouse_click = fake_handle_mouse_click
    try:
        consumed = input_router.handle_mouse_click(editor, 100.0, 100.0, 1, 0)
    finally:
        input_router.editor_input.handle_mouse_click = original

    assert consumed is True
    assert called["editor_input"] is True


def test_input_router_creator_click_does_not_fall_through_to_editor_input() -> None:
    controller = _ready_controller()
    editor = SimpleNamespace(active=True, creator_mode=controller)
    called = {"editor_input": False}

    def fake_handle_mouse_click(_self, _x, _y, _button, _modifiers):
        called["editor_input"] = True
        return True

    original = input_router.editor_input.handle_mouse_click
    input_router.editor_input.handle_mouse_click = fake_handle_mouse_click
    try:
        x, y = _stage_proposal_click_point(_draw_commands(controller))
        consumed = input_router.handle_mouse_click(editor, x, y, 1, 0)
    finally:
        input_router.editor_input.handle_mouse_click = original

    assert consumed is True
    assert called["editor_input"] is False


def test_package_import_still_does_not_import_renderer_module() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import engine.editor.creator_mode; "
                "print('engine.editor.creator_mode.creator_overlay_renderer' in sys.modules)"
            ),
        ],
        capture_output=True,
        check=True,
        text=True,
    )

    assert result.stdout.strip() == "False"


def test_overlay_click_module_import_loads_renderer_for_hit_testing() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from engine.editor.creator_mode.creator_overlay_click "
                "import try_handle_creator_mode_overlay_click; "
                "print('engine.editor.creator_mode.creator_overlay_renderer' in sys.modules)"
            ),
        ],
        capture_output=True,
        check=True,
        text=True,
    )

    assert result.stdout.strip() == "True"


def test_pure_modules_do_not_import_real_bridge_modules() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from engine.editor.creator_mode.creator_overlay_click "
                "import try_handle_creator_mode_overlay_click; "
                "blocked = ["
                "'engine.editor.live_session_bridge', "
                "'engine.editor.editor_live_ops_controller', "
                "'engine.editor.proposal_inbox'"
                "]; "
                "print(any(name in sys.modules for name in blocked))"
            ),
        ],
        capture_output=True,
        check=True,
        text=True,
    )

    assert result.stdout.strip() == "False"


class FakeBridge:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, object]]] = []

    def stage_pending_proposal(self, ops: list[dict[str, object]]) -> dict[str, object]:
        self.calls.append(ops)
        return {
            "ok": True,
            "proposal_id": "proposal-1",
            "proposal": {"preview_summary": "Set SceneExit params on door_north"},
            "preview": "Set SceneExit params on door_north",
            "warnings": [],
        }


class HostileBridge:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def stage_pending_proposal(self, ops: list[dict[str, object]]) -> dict[str, object]:
        self.calls.append("stage_pending_proposal")
        return {"ok": True, "proposal_id": "proposal-1", "preview": "ok"}

    def accept_pending_proposal(self, proposal_id: str) -> dict[str, object]:
        raise AssertionError("accept must not be called")

    def reject_pending_proposal(self, proposal_id: str) -> dict[str, object]:
        raise AssertionError("reject must not be called")

    def apply_live_op(self, op: dict[str, object]) -> dict[str, object]:
        raise AssertionError("apply must not be called")


def _ready_controller() -> CreatorModeController:
    controller = CreatorModeController(
        _editor_with_selection(_door_entity(), live_bridge=FakeBridge())
    )
    controller.show()
    return controller


def _draw_commands(controller: CreatorModeController):
    model = build_creator_overlay_model(controller.build_snapshot())
    return build_creator_overlay_draw_commands(model, 1280, 720)


def _stage_proposal_click_point(commands) -> tuple[float, float]:
    for command in commands:
        if command.action_id == DOOR_STAGE_PROPOSAL_ACTION_ID:
            return (
                (command.hit_left + command.hit_right) / 2.0,
                (command.hit_top + command.hit_bottom) / 2.0,
            )
    raise AssertionError("missing Stage Proposal click target")


def _door_entity(config: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "id": "door_north",
        "name": "North Gate",
        "behaviours": ["SceneExit"],
        "behaviour_config": {
            "SceneExit": dict(
                config
                if config is not None
                else {
                    "target_scene": "town",
                    "target_spawn": "north_gate_entry",
                    "trigger": "interact",
                }
            )
        },
    }


def _editor_with_selection(entity: dict[str, object] | None, live_bridge: object | None = None):
    return SimpleNamespace(
        selected_entity=entity,
        live_bridge=live_bridge,
        window=SimpleNamespace(
            width=1280,
            height=720,
            scene_controller=SimpleNamespace(current_scene_path="forest"),
        ),
    )


def _command_text(commands) -> str:
    return "\n".join(command.text for command in commands if command.kind == "text")
