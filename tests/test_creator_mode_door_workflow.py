from __future__ import annotations

import subprocess
import sys

import pytest

from engine.editor.creator_mode import (
    CreatorDoorPlanRequest,
    CreatorDoorWorkflowRequest,
    build_creator_door_workflow,
    build_creator_door_workflow_from_plan_request,
)
from engine.editor.creator_mode.creator_door_workflow import CreatorDoorWorkflowModel

pytestmark = pytest.mark.fast


def test_valid_workflow_returns_ok_plan_and_ready_preview() -> None:
    workflow = build_creator_door_workflow(
        CreatorDoorWorkflowRequest(source_scene="forest", destination_scene="town")
    )

    assert workflow.plan.ok is True
    assert workflow.preview.status == "ready"


def test_invalid_workflow_returns_blocked_preview() -> None:
    workflow = build_creator_door_workflow(
        CreatorDoorWorkflowRequest(source_scene="", destination_scene="town")
    )

    assert workflow.plan.ok is False
    assert workflow.preview.status == "blocked"
    assert "Source scene is required." in workflow.preview.errors


def test_workflow_preserves_warning_from_missing_destination_spawn() -> None:
    workflow = build_creator_door_workflow(
        CreatorDoorWorkflowRequest(source_scene="forest", destination_scene="town")
    )

    assert workflow.plan.warnings == ("Door has no destination spawn point.",)
    assert workflow.preview.warnings == ("Door has no destination spawn point.",)


def test_workflow_includes_disabled_preview_actions() -> None:
    workflow = build_creator_door_workflow(_locked_workflow_request())

    actions = {action.label: action for action in workflow.preview.actions}
    assert actions["Stage Proposal"].enabled is False
    assert actions["Apply Changes"].enabled is False


def test_locked_workflow_includes_lock_plan_operation_and_preview_step() -> None:
    workflow = build_creator_door_workflow(_locked_workflow_request())

    assert "configure_lock" in {operation.op for operation in workflow.plan.operations}
    assert "Set lock" in {step.title for step in workflow.preview.steps}


def test_workflow_request_is_not_mutated() -> None:
    request = _locked_workflow_request()
    before = _workflow_request_snapshot(request)

    build_creator_door_workflow(request)

    assert _workflow_request_snapshot(request) == before


def test_workflow_from_plan_request_matches_normal_workflow() -> None:
    plan_request = CreatorDoorPlanRequest(
        source_scene="forest",
        destination_scene="town",
        destination_spawn_id="north_gate_entry",
        door_name="North Gate",
        source_entity_id="door_north",
        locked=True,
        required_flag="gate_unlocked",
    )
    workflow_request = CreatorDoorWorkflowRequest(
        source_scene="forest",
        destination_scene="town",
        destination_spawn_id="north_gate_entry",
        door_name="North Gate",
        source_entity_id="door_north",
        locked=True,
        required_flag="gate_unlocked",
    )

    assert _workflow_snapshot(
        build_creator_door_workflow_from_plan_request(plan_request)
    ) == _workflow_snapshot(build_creator_door_workflow(workflow_request))


def test_whitespace_trimming_passes_through_plan_and_preview() -> None:
    workflow = build_creator_door_workflow(
        CreatorDoorWorkflowRequest(
            source_scene=" forest ",
            destination_scene=" town ",
            destination_spawn_id=" north_gate_entry ",
            door_name=" North Gate ",
            source_entity_id=" door_north ",
            trigger=" touch ",
        )
    )

    assert workflow.plan.title == "Door plan: North Gate"
    assert workflow.plan.summary == "Plan door from forest to town at north_gate_entry."
    assert _step(workflow, "Configure selected door").detail == (
        "Destination: Town. Arrival point: north_gate_entry. Use: Touch."
    )


def test_invalid_trigger_stays_blocked() -> None:
    workflow = build_creator_door_workflow(
        CreatorDoorWorkflowRequest(
            source_scene="forest",
            destination_scene="town",
            trigger="script",
        )
    )

    assert workflow.plan.ok is False
    assert workflow.preview.status == "blocked"
    assert "Trigger must be one of: interact, touch, auto." in workflow.preview.errors


def test_workflow_module_imports_without_arcade() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "sys.modules['arcade'] = None; "
                "from engine.editor.creator_mode.creator_door_workflow "
                "import build_creator_door_workflow; "
                "print(callable(build_creator_door_workflow))"
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


def _locked_workflow_request() -> CreatorDoorWorkflowRequest:
    return CreatorDoorWorkflowRequest(
        source_scene="forest",
        destination_scene="town",
        destination_spawn_id="north_gate_entry",
        door_name="North Gate",
        source_entity_id="door_north",
        locked=True,
        required_flag="gate_unlocked",
    )


def _step(workflow: CreatorDoorWorkflowModel, title: str):
    return next(step for step in workflow.preview.steps if step.title == title)


def _workflow_request_snapshot(request: CreatorDoorWorkflowRequest):
    return (
        request.source_scene,
        request.destination_scene,
        request.destination_spawn_id,
        request.door_name,
        request.source_entity_id,
        request.locked,
        request.required_flag,
        request.trigger,
        request.transition_behaviour,
        request.scene_exit_listen_event,
        request.interactable_event,
        request.entity_require_flags,
    )


def _workflow_snapshot(workflow: CreatorDoorWorkflowModel):
    return (
        workflow.plan.ok,
        workflow.plan.title,
        workflow.plan.summary,
        tuple(
            (operation.op, operation.target, dict(operation.payload))
            for operation in workflow.plan.operations
        ),
        workflow.plan.errors,
        workflow.plan.warnings,
        workflow.preview.title,
        workflow.preview.summary,
        workflow.preview.status,
        tuple(
            (step.title, step.detail, step.severity)
            for step in workflow.preview.steps
        ),
        tuple(
            (action.label, action.enabled, action.reason)
            for action in workflow.preview.actions
        ),
        workflow.preview.errors,
        workflow.preview.warnings,
    )
