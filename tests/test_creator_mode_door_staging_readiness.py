from __future__ import annotations

import subprocess
import sys

import pytest

from engine.editor.creator_mode import (
    CreatorDoorWorkflowRequest,
    build_creator_door_staging_readiness,
    build_creator_door_workflow,
    creator_door_staging,
)
from engine.editor.creator_mode.creator_door_staging_readiness import _preview_live_op

pytestmark = pytest.mark.fast


def test_valid_existing_door_workflow_with_fake_bridge_is_ready() -> None:
    bridge = FakeBridge()

    model = build_creator_door_staging_readiness(
        build_creator_door_workflow(_existing_door_request()),
        bridge,
    )

    assert model.status == "ready"
    assert model.summary == "This door proposal is ready to stage."
    assert bridge.called is False


def test_ready_model_has_stage_proposal_action_enabled() -> None:
    model = build_creator_door_staging_readiness(
        build_creator_door_workflow(_existing_door_request()),
        FakeBridge(),
    )

    action = model.actions[0]
    assert action.label == "Stage Proposal"
    assert action.enabled is True
    assert action.reason == ""


def test_ready_model_includes_live_op_preview_text() -> None:
    model = build_creator_door_staging_readiness(
        build_creator_door_workflow(_existing_door_request()),
        FakeBridge(),
    )

    assert model.live_ops_preview == ("Set SceneTransition params on door_north.",)


def test_missing_bridge_returns_bridge_unavailable() -> None:
    model = build_creator_door_staging_readiness(
        build_creator_door_workflow(_existing_door_request()),
        None,
    )

    assert model.status == "bridge_unavailable"
    assert model.summary == "The proposal bridge is not available."
    assert model.errors == ("Proposal bridge is unavailable.",)


def test_bridge_without_stage_pending_proposal_returns_bridge_unavailable() -> None:
    model = build_creator_door_staging_readiness(
        build_creator_door_workflow(_existing_door_request()),
        object(),
    )

    assert model.status == "bridge_unavailable"
    assert model.errors == ("Proposal bridge is unavailable.",)


def test_bridge_unavailable_model_has_stage_proposal_action_disabled() -> None:
    model = build_creator_door_staging_readiness(
        build_creator_door_workflow(_existing_door_request()),
        None,
    )

    action = model.actions[0]
    assert action.label == "Stage Proposal"
    assert action.enabled is False
    assert action.reason == "Proposal bridge is unavailable."


def test_blocked_workflow_returns_blocked() -> None:
    model = build_creator_door_staging_readiness(
        build_creator_door_workflow(
            CreatorDoorWorkflowRequest(source_scene="", destination_scene="town")
        ),
        FakeBridge(),
    )

    assert model.status == "blocked"
    assert model.summary == "This door proposal cannot be staged yet."


def test_unrepresentable_workflow_returns_blocked() -> None:
    model = build_creator_door_staging_readiness(
        build_creator_door_workflow(
            CreatorDoorWorkflowRequest(source_scene="forest", destination_scene="town")
        ),
        FakeBridge(),
    )

    assert model.status == "blocked"
    assert model.errors == ("Door workflow cannot be represented by current live ops.",)


def test_blocked_model_has_stage_proposal_action_disabled() -> None:
    model = build_creator_door_staging_readiness(
        build_creator_door_workflow(
            CreatorDoorWorkflowRequest(source_scene="", destination_scene="town")
        ),
        FakeBridge(),
    )

    action = model.actions[0]
    assert action.label == "Stage Proposal"
    assert action.enabled is False
    assert action.reason == "Door workflow is blocked."


def test_errors_pass_through_from_live_op_conversion() -> None:
    model = build_creator_door_staging_readiness(
        build_creator_door_workflow(
            CreatorDoorWorkflowRequest(source_scene="", destination_scene="town")
        ),
        FakeBridge(),
    )

    assert model.errors == ("Door workflow is blocked.", "Source scene is required.")


def test_warnings_pass_through() -> None:
    model = build_creator_door_staging_readiness(
        build_creator_door_workflow(
            CreatorDoorWorkflowRequest(
                source_scene="forest",
                destination_scene="town",
                source_entity_id="door_north",
            )
        ),
        FakeBridge(),
    )

    assert model.warnings == ("Door has no destination spawn point.",)


def test_readiness_builder_does_not_call_bridge_stage_pending_proposal() -> None:
    bridge = FakeBridge()

    build_creator_door_staging_readiness(
        build_creator_door_workflow(_existing_door_request()),
        bridge,
    )

    assert bridge.called is False


def test_readiness_builder_does_not_call_stage_creator_door_proposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args, **_kwargs):
        raise AssertionError("readiness must not stage")

    monkeypatch.setattr(creator_door_staging, "stage_creator_door_proposal", fail)

    model = build_creator_door_staging_readiness(
        build_creator_door_workflow(_existing_door_request()),
        FakeBridge(),
    )

    assert model.status == "ready"


def test_live_ops_preview_is_deterministic() -> None:
    workflow = build_creator_door_workflow(_existing_door_request())

    first = build_creator_door_staging_readiness(workflow, FakeBridge())
    second = build_creator_door_staging_readiness(workflow, FakeBridge())

    assert first.live_ops_preview == second.live_ops_preview


def test_unknown_live_op_preview_is_safe() -> None:
    assert _preview_live_op({"type": "custom_op", "params": {"x": object()}}) == "Live op: custom_op"


def test_module_imports_without_arcade() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "sys.modules['arcade'] = None; "
                "from engine.editor.creator_mode.creator_door_staging_readiness "
                "import build_creator_door_staging_readiness; "
                "print(callable(build_creator_door_staging_readiness))"
            ),
        ],
        capture_output=True,
        check=True,
        text=True,
    )

    assert result.stdout.strip() == "True"


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


def test_module_does_not_import_real_bridge_modules() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from engine.editor.creator_mode.creator_door_staging_readiness "
                "import build_creator_door_staging_readiness; "
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
        self.called = False

    def stage_pending_proposal(self, ops):
        self.called = True
        raise AssertionError("readiness must not stage")


def _existing_door_request() -> CreatorDoorWorkflowRequest:
    return CreatorDoorWorkflowRequest(
        source_scene="forest",
        destination_scene="town",
        destination_spawn_id="north_gate_entry",
        source_entity_id="door_north",
    )
