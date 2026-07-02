from __future__ import annotations

import subprocess
import sys

import pytest

from engine.editor.creator_mode import (
    CreatorDoorPlanRequest,
    build_creator_door_plan,
    build_creator_door_preview,
)
from engine.editor.creator_mode.creator_door_plan import (
    CreatorDoorPlan,
    CreatorDoorPlanOperation,
)

pytestmark = pytest.mark.fast


def test_ok_door_plan_becomes_ready_preview() -> None:
    preview = build_creator_door_preview(_locked_preview_plan())

    assert preview.status == "ready"
    assert preview.title == "Door plan: North Gate"
    assert preview.summary == "Plan door from forest to town at north_gate_entry."
    assert preview.errors == ()


def test_invalid_plan_becomes_blocked_preview() -> None:
    plan = build_creator_door_plan(
        CreatorDoorPlanRequest(source_scene="", destination_scene="town")
    )

    preview = build_creator_door_preview(plan)

    assert preview.status == "blocked"
    assert preview.summary == "Fix the listed problems before this door can be planned."
    assert preview.steps == ()
    assert "Source scene is required." in preview.errors


def test_ready_preview_includes_disabled_stage_proposal_action() -> None:
    preview = build_creator_door_preview(_locked_preview_plan())

    action = _action(preview, "Stage Proposal")
    assert action.enabled is False
    assert action.reason == "Proposal staging is not available in this slice."


def test_ready_preview_includes_disabled_apply_changes_action() -> None:
    preview = build_creator_door_preview(_locked_preview_plan())

    action = _action(preview, "Apply Changes")
    assert action.enabled is False
    assert action.reason == "Creator Mode cannot apply door plans yet."


def test_ensure_door_entity_maps_to_prepare_door() -> None:
    preview = build_creator_door_preview(_locked_preview_plan())

    step = _step(preview, "Prepare door")
    assert step.detail == "Prepare door_north in the source map."


def test_configure_scene_exit_maps_to_set_destination() -> None:
    preview = build_creator_door_preview(_locked_preview_plan())

    step = _step(preview, "Set destination")
    assert "town" in step.detail


def test_configure_lock_maps_to_set_lock() -> None:
    preview = build_creator_door_preview(_locked_preview_plan())

    step = _step(preview, "Set lock")
    assert step.detail == "Keep the door locked until gate_unlocked is set."


def test_destination_step_includes_destination_scene_spawn_and_trigger() -> None:
    preview = build_creator_door_preview(_locked_preview_plan())

    detail = _step(preview, "Set destination").detail
    assert "town" in detail
    assert "north_gate_entry" in detail
    assert "interact" in detail


def test_lock_step_includes_required_flag() -> None:
    preview = build_creator_door_preview(_locked_preview_plan())

    assert "gate_unlocked" in _step(preview, "Set lock").detail


def test_missing_target_says_new_door() -> None:
    plan = build_creator_door_plan(
        CreatorDoorPlanRequest(source_scene="forest", destination_scene="town")
    )

    preview = build_creator_door_preview(plan)

    assert _step(preview, "Prepare door").detail == "Prepare new door in the source map."


def test_unknown_operation_maps_safely() -> None:
    plan = CreatorDoorPlan(
        ok=True,
        title="Door plan",
        summary="Plan door.",
        operations=(
            CreatorDoorPlanOperation(
                op="custom_internal_step",
                target="door_north",
                payload={"secret": object()},
            ),
        ),
        errors=(),
        warnings=(),
    )

    preview = build_creator_door_preview(plan)

    assert preview.steps[0].title == "Plan step"
    assert preview.steps[0].detail == "Review planned operation custom_internal_step."


def test_errors_and_warnings_pass_through() -> None:
    plan = CreatorDoorPlan(
        ok=False,
        title="Door plan",
        summary="Broken.",
        operations=(),
        errors=("Problem one.",),
        warnings=("Warning one.",),
    )

    preview = build_creator_door_preview(plan)

    assert preview.errors == ("Problem one.",)
    assert preview.warnings == ("Warning one.",)


def test_preview_builder_does_not_mutate_plan() -> None:
    plan = _locked_preview_plan()
    before = _plan_snapshot(plan)

    build_creator_door_preview(plan)

    assert _plan_snapshot(plan) == before


def test_preview_module_imports_without_arcade() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "sys.modules['arcade'] = None; "
                "from engine.editor.creator_mode.creator_door_preview import build_creator_door_preview; "
                "print(callable(build_creator_door_preview))"
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


def _locked_preview_plan() -> CreatorDoorPlan:
    return build_creator_door_plan(
        CreatorDoorPlanRequest(
            source_scene="forest",
            destination_scene="town",
            destination_spawn_id="north_gate_entry",
            door_name="North Gate",
            source_entity_id="door_north",
            locked=True,
            required_flag="gate_unlocked",
        )
    )


def _step(preview, title: str):
    return next(step for step in preview.steps if step.title == title)


def _action(preview, label: str):
    return next(action for action in preview.actions if action.label == label)


def _plan_snapshot(plan: CreatorDoorPlan):
    return (
        plan.ok,
        plan.title,
        plan.summary,
        tuple((operation.op, operation.target, dict(operation.payload)) for operation in plan.operations),
        plan.errors,
        plan.warnings,
    )
