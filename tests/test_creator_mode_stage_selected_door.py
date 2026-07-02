from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace

import pytest

from engine.editor.creator_mode import (
    CreatorModeController,
    build_creator_overlay_model,
)
from engine.editor.creator_mode import creator_door_staging
from engine.editor.creator_mode.creator_overlay_renderer import build_creator_overlay_draw_commands

pytestmark = pytest.mark.fast


def test_valid_selected_door_stages_through_fake_bridge_when_explicitly_called() -> None:
    bridge = FakeBridge()
    controller = CreatorModeController(_editor_with_selection(_door_entity(), live_bridge=bridge))

    result = controller.stage_selected_door_proposal()

    assert result.ok is True
    assert result.proposal_id == "proposal-1"
    assert result.preview_summary == "Set SceneExit params on door_north"
    assert len(bridge.calls) == 1


def test_fake_bridge_receives_exactly_one_stage_pending_proposal_call() -> None:
    bridge = FakeBridge()
    controller = CreatorModeController(_editor_with_selection(_door_entity(), live_bridge=bridge))

    controller.stage_selected_door_proposal()

    assert len(bridge.calls) == 1


def test_fake_bridge_receives_list_of_plain_dict_ops() -> None:
    bridge = FakeBridge()
    controller = CreatorModeController(_editor_with_selection(_door_entity(), live_bridge=bridge))

    controller.stage_selected_door_proposal()

    ops = bridge.calls[0]
    assert isinstance(ops, list)
    assert len(ops) == 1
    assert isinstance(ops[0], dict)
    assert isinstance(ops[0]["params"], dict)


def test_result_includes_proposal_id_from_fake_bridge() -> None:
    controller = CreatorModeController(
        _editor_with_selection(_door_entity(), live_bridge=FakeBridge())
    )

    result = controller.stage_selected_door_proposal()

    assert result.proposal_id == "proposal-1"


def test_non_door_selection_returns_not_stageable_and_does_not_call_bridge() -> None:
    bridge = FakeBridge()
    controller = CreatorModeController(
        _editor_with_selection({"name": "Rock", "behaviours": ["StaticSprite"]}, live_bridge=bridge)
    )

    result = controller.stage_selected_door_proposal()

    assert result.ok is False
    assert result.errors == ("No stageable door is selected.",)
    assert bridge.calls == []


def test_missing_selection_returns_not_stageable() -> None:
    controller = CreatorModeController(
        SimpleNamespace(
            selected_entity=None,
            live_bridge=FakeBridge(),
            window=SimpleNamespace(scene_controller=SimpleNamespace(current_scene_path="forest")),
        )
    )

    result = controller.stage_selected_door_proposal()

    assert result.ok is False
    assert result.errors == ("No stageable door is selected.",)


def test_missing_bridge_returns_unavailable() -> None:
    controller = CreatorModeController(_editor_with_selection(_door_entity(), live_bridge=None))

    result = controller.stage_selected_door_proposal()

    assert result.ok is False
    assert result.errors == ("Proposal bridge is unavailable.",)


def test_selected_door_missing_destination_returns_false_and_does_not_call_bridge() -> None:
    bridge = FakeBridge()
    entity = _door_entity(config={"target_spawn": "north_gate_entry"})
    controller = CreatorModeController(_editor_with_selection(entity, live_bridge=bridge))

    result = controller.stage_selected_door_proposal()

    assert result.ok is False
    assert "Destination scene is required." in result.errors
    assert bridge.calls == []


def test_hostile_bridge_accept_reject_apply_are_not_called() -> None:
    bridge = HostileBridge()
    controller = CreatorModeController(_editor_with_selection(_door_entity(), live_bridge=bridge))

    result = controller.stage_selected_door_proposal()

    assert result.ok is True
    assert bridge.calls == ["stage_pending_proposal"]


def test_build_snapshot_does_not_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args, **_kwargs):
        raise AssertionError("build_snapshot must not stage")

    monkeypatch.setattr(creator_door_staging, "stage_creator_door_proposal", fail)
    controller = CreatorModeController(_editor_with_selection(_door_entity(), live_bridge=FakeBridge()))
    controller.show()

    controller.build_snapshot()


def test_build_creator_overlay_model_does_not_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args, **_kwargs):
        raise AssertionError("overlay model must not stage")

    monkeypatch.setattr(creator_door_staging, "stage_creator_door_proposal", fail)
    controller = CreatorModeController(_editor_with_selection(_door_entity(), live_bridge=FakeBridge()))
    controller.show()

    build_creator_overlay_model(controller.build_snapshot())


def test_build_creator_overlay_draw_commands_does_not_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args, **_kwargs):
        raise AssertionError("draw commands must not stage")

    monkeypatch.setattr(creator_door_staging, "stage_creator_door_proposal", fail)
    controller = CreatorModeController(_editor_with_selection(_door_entity(), live_bridge=FakeBridge()))
    controller.show()
    model = build_creator_overlay_model(controller.build_snapshot())

    commands = build_creator_overlay_draw_commands(model, 1280, 720)

    assert "[Ready] Stage Proposal" in _command_text(commands)


def test_stage_proposal_render_text_remains_display_only() -> None:
    controller = CreatorModeController(_editor_with_selection(_door_entity(), live_bridge=FakeBridge()))
    controller.show()

    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        1280,
        720,
    )
    text = _command_text(commands)

    assert "[Ready] Stage Proposal" in text
    assert "[Disabled] Stage Proposal" not in text


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


def test_controller_method_does_not_import_real_bridge_modules() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from engine.editor.creator_mode.creator_mode_controller "
                "import CreatorModeController; "
                "from types import SimpleNamespace; "
                "controller = CreatorModeController("
                "SimpleNamespace("
                "selected_entity=None, live_bridge=None, "
                "window=SimpleNamespace(scene_controller=SimpleNamespace(current_scene_path=''))"
                ")); "
                "controller.stage_selected_door_proposal(); "
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
        window=SimpleNamespace(scene_controller=SimpleNamespace(current_scene_path="forest")),
    )


def _command_text(commands) -> str:
    return "\n".join(command.text for command in commands if command.kind == "text")
