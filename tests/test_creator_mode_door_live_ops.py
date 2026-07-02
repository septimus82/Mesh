from __future__ import annotations

import copy
import subprocess
import sys

import pytest

from engine.editor.creator_mode import (
    CreatorDoorLiveOpsResult,
    CreatorDoorPlan,
    CreatorDoorPlanOperation,
    CreatorDoorWorkflowRequest,
    build_creator_door_live_ops,
    build_creator_door_workflow,
)
from engine.editor.creator_mode.creator_door_preview import build_creator_door_preview
from engine.editor.creator_mode.creator_door_workflow import CreatorDoorWorkflowModel

pytestmark = pytest.mark.fast


def test_blocked_workflow_returns_false_and_includes_plan_errors() -> None:
    workflow = build_creator_door_workflow(
        CreatorDoorWorkflowRequest(source_scene="", destination_scene="town")
    )

    result = build_creator_door_live_ops(workflow)

    assert result.ok is False
    assert result.ops == ()
    assert "Door workflow is blocked." in result.errors
    assert "Source scene is required." in result.errors


def test_unsupported_operation_returns_false_and_names_operation() -> None:
    workflow = _workflow_with_operations(
        (
            _operation("ensure_door_entity"),
            _operation("configure_scene_exit"),
            _operation("custom_step"),
        )
    )

    result = build_creator_door_live_ops(workflow)

    assert result.ok is False
    assert result.ops == ()
    assert result.errors == ("Unsupported door plan operation: custom_step.",)


def test_missing_source_entity_id_fails_closed_without_door_creation() -> None:
    workflow = build_creator_door_workflow(
        CreatorDoorWorkflowRequest(source_scene="forest", destination_scene="town")
    )

    result = build_creator_door_live_ops(workflow)

    assert result.ok is False
    assert result.ops == ()
    assert result.errors == (
        "Door workflow cannot be represented by current live ops.",
    )


def test_existing_door_converts_scene_exit_to_supported_live_op_schema() -> None:
    workflow = build_creator_door_workflow(_existing_door_request())

    result = build_creator_door_live_ops(workflow)

    assert result.ok is True
    assert _ops_snapshot(result) == (
        (
            "set_behaviour_params",
            "forest",
            "door_north",
            "SceneExit",
            (
                ("target_scene", "town"),
                ("target_spawn", "north_gate_entry"),
                ("trigger", "interact"),
            ),
        ),
    )


def test_result_op_and_params_are_plain_dicts() -> None:
    workflow = build_creator_door_workflow(_existing_door_request())

    result = build_creator_door_live_ops(workflow)

    assert isinstance(result.ops[0], dict)
    assert isinstance(result.ops[0]["params"], dict)


def test_result_ops_can_be_deep_copied_like_bridge_ops() -> None:
    workflow = build_creator_door_workflow(_existing_door_request())
    result = build_creator_door_live_ops(workflow)

    copied = copy.deepcopy(list(result.ops))

    assert copied == list(result.ops)


def test_adapter_output_is_bridge_compatible_shape() -> None:
    workflow = build_creator_door_workflow(_existing_door_request())
    result = build_creator_door_live_ops(workflow)

    ops = list(result.ops)

    assert isinstance(ops, list)
    assert isinstance(ops[0], dict)
    assert ops[0]["type"] == "set_behaviour_params"
    assert isinstance(ops[0]["params"], dict)
    assert "entity_id" in ops[0]
    assert "behaviour_name" in ops[0]


def test_locked_existing_door_includes_required_flag_in_live_op_payload() -> None:
    workflow = build_creator_door_workflow(
        CreatorDoorWorkflowRequest(
            source_scene="forest",
            destination_scene="town",
            destination_spawn_id="north_gate_entry",
            source_entity_id="door_north",
            locked=True,
            required_flag="gate_unlocked",
        )
    )

    result = build_creator_door_live_ops(workflow)

    assert result.ok is True
    params = dict(result.ops[0]["params"])  # type: ignore[arg-type]
    assert params["locked"] is True
    assert params["requires_flag"] == "gate_unlocked"


def test_warnings_pass_through() -> None:
    workflow = build_creator_door_workflow(
        CreatorDoorWorkflowRequest(
            source_scene="forest",
            destination_scene="town",
            source_entity_id="door_north",
        )
    )

    result = build_creator_door_live_ops(workflow)

    assert result.warnings == ("Door has no destination spawn point.",)


def test_result_ops_are_deterministic() -> None:
    workflow = build_creator_door_workflow(_existing_door_request())

    first = build_creator_door_live_ops(workflow)
    second = build_creator_door_live_ops(workflow)

    assert _ops_snapshot(first) == _ops_snapshot(second)


def test_workflow_object_is_not_mutated() -> None:
    workflow = build_creator_door_workflow(_existing_door_request())
    before = _workflow_snapshot(workflow)

    build_creator_door_live_ops(workflow)

    assert _workflow_snapshot(workflow) == before


def test_adapter_module_imports_without_arcade() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "sys.modules['arcade'] = None; "
                "from engine.editor.creator_mode.creator_door_live_ops "
                "import build_creator_door_live_ops; "
                "print(callable(build_creator_door_live_ops))"
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


def test_adapter_does_not_import_live_bridge_live_ops_or_proposal_inbox() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from engine.editor.creator_mode.creator_door_live_ops "
                "import build_creator_door_live_ops; "
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


def _existing_door_request() -> CreatorDoorWorkflowRequest:
    return CreatorDoorWorkflowRequest(
        source_scene="forest",
        destination_scene="town",
        destination_spawn_id="north_gate_entry",
        source_entity_id="door_north",
    )


def _operation(op: str) -> CreatorDoorPlanOperation:
    return CreatorDoorPlanOperation(op=op, target="door_north", payload=_payload())


def _payload() -> dict[str, object]:
    return {
        "source_scene": "forest",
        "destination_scene": "town",
        "destination_spawn_id": "north_gate_entry",
        "door_name": "North Gate",
        "source_entity_id": "door_north",
        "locked": False,
        "required_flag": "",
        "trigger": "interact",
    }


def _workflow_with_operations(
    operations: tuple[CreatorDoorPlanOperation, ...],
) -> CreatorDoorWorkflowModel:
    plan = CreatorDoorPlan(
        ok=True,
        title="Door plan",
        summary="Plan door.",
        operations=operations,
        errors=(),
        warnings=(),
    )
    return CreatorDoorWorkflowModel(
        plan=plan,
        preview=build_creator_door_preview(plan),
    )


def _ops_snapshot(result: CreatorDoorLiveOpsResult):
    return tuple(
        (
            op.get("type"),
            op.get("scene_path"),
            op.get("entity_id"),
            op.get("behaviour_name"),
            tuple(dict(op.get("params", {})).items()),
        )
        for op in result.ops
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
        workflow.preview.status,
        tuple((step.title, step.detail) for step in workflow.preview.steps),
    )
