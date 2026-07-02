from __future__ import annotations

import copy
import subprocess
import sys

import pytest

from engine.editor.creator_mode import (
    CreatorDoorWorkflowRequest,
    build_creator_door_workflow,
    stage_creator_door_proposal,
)

pytestmark = pytest.mark.fast


def test_valid_existing_door_workflow_stages_through_fake_bridge() -> None:
    bridge = FakeBridge()
    workflow = build_creator_door_workflow(_existing_door_request())

    result = stage_creator_door_proposal(workflow, bridge)

    assert result.ok is True
    assert result.proposal_id == "proposal-1"
    assert result.preview_summary == "Set SceneExit params on 'door_north'"
    assert len(bridge.calls) == 1


def test_fake_bridge_receives_list_not_tuple() -> None:
    bridge = FakeBridge()

    stage_creator_door_proposal(build_creator_door_workflow(_existing_door_request()), bridge)

    assert isinstance(bridge.calls[0], list)


def test_fake_bridge_receives_plain_dict_op_and_params() -> None:
    bridge = FakeBridge()

    stage_creator_door_proposal(build_creator_door_workflow(_existing_door_request()), bridge)

    op = bridge.calls[0][0]
    assert isinstance(op, dict)
    assert isinstance(op["params"], dict)


def test_fake_bridge_receives_deep_copied_ops_not_same_object() -> None:
    bridge = IdentityBridge()
    workflow = build_creator_door_workflow(_existing_door_request())

    stage_creator_door_proposal(workflow, bridge)

    assert bridge.ops is not None
    assert bridge.ops is not list(workflow.plan.operations)
    bridge.ops[0]["params"]["target_scene"] = "mutated"
    result = stage_creator_door_proposal(workflow, FakeBridge())
    assert result.preview_summary == "Set SceneExit params on 'door_north'"


def test_blocked_workflow_does_not_call_bridge() -> None:
    bridge = FakeBridge()
    workflow = build_creator_door_workflow(
        CreatorDoorWorkflowRequest(source_scene="", destination_scene="town")
    )

    result = stage_creator_door_proposal(workflow, bridge)

    assert result.ok is False
    assert result.errors[0] == "Door workflow is blocked."
    assert bridge.calls == []


def test_live_op_conversion_failure_does_not_call_bridge() -> None:
    bridge = FakeBridge()
    workflow = build_creator_door_workflow(
        CreatorDoorWorkflowRequest(source_scene="forest", destination_scene="town")
    )

    result = stage_creator_door_proposal(workflow, bridge)

    assert result.ok is False
    assert result.errors == ("Door workflow cannot be represented by current live ops.",)
    assert bridge.calls == []


def test_missing_bridge_returns_unavailable() -> None:
    workflow = build_creator_door_workflow(_existing_door_request())

    result = stage_creator_door_proposal(workflow, None)

    assert result.ok is False
    assert result.errors == ("Proposal bridge is unavailable.",)


def test_bridge_missing_stage_pending_proposal_returns_unavailable() -> None:
    workflow = build_creator_door_workflow(_existing_door_request())

    result = stage_creator_door_proposal(workflow, object())

    assert result.ok is False
    assert result.errors == ("Proposal bridge is unavailable.",)


def test_bridge_failure_result_returns_false_and_includes_message() -> None:
    workflow = build_creator_door_workflow(_existing_door_request())

    result = stage_creator_door_proposal(workflow, FailureBridge())

    assert result.ok is False
    assert result.errors == ("dry-run failed",)


def test_bridge_exception_returns_false_and_generic_error() -> None:
    workflow = build_creator_door_workflow(_existing_door_request())

    result = stage_creator_door_proposal(workflow, ExceptionBridge())

    assert result.ok is False
    assert result.errors == ("Failed to stage door proposal.",)


def test_result_includes_proposal_id_from_bridge_success_response() -> None:
    result = stage_creator_door_proposal(
        build_creator_door_workflow(_existing_door_request()),
        FakeBridge(),
    )

    assert result.proposal_id == "proposal-1"


def test_result_includes_preview_summary_from_bridge_success_response() -> None:
    result = stage_creator_door_proposal(
        build_creator_door_workflow(_existing_door_request()),
        FakeBridge(),
    )

    assert result.preview_summary == "Set SceneExit params on 'door_north'"


def test_result_uses_bridge_preview_when_proposal_summary_missing() -> None:
    result = stage_creator_door_proposal(
        build_creator_door_workflow(_existing_door_request()),
        PreviewOnlyBridge(),
    )

    assert result.preview_summary == "Preview fallback"


def test_warnings_from_live_op_conversion_pass_through() -> None:
    workflow = build_creator_door_workflow(
        CreatorDoorWorkflowRequest(
            source_scene="forest",
            destination_scene="town",
            source_entity_id="door_north",
        )
    )

    result = stage_creator_door_proposal(workflow, FakeBridge())

    assert result.ok is True
    assert result.warnings == ("Door has no destination spawn point.",)


def test_bridge_warnings_are_appended() -> None:
    result = stage_creator_door_proposal(
        build_creator_door_workflow(_existing_door_request()),
        WarningBridge(),
    )

    assert result.warnings == ("bridge warning",)


def test_no_accept_reject_or_apply_method_is_called_on_bridge() -> None:
    bridge = HostileBridge()

    result = stage_creator_door_proposal(
        build_creator_door_workflow(_existing_door_request()),
        bridge,
    )

    assert result.ok is True
    assert bridge.calls == ["stage_pending_proposal"]


def test_staging_module_imports_without_arcade() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "sys.modules['arcade'] = None; "
                "from engine.editor.creator_mode.creator_door_staging "
                "import stage_creator_door_proposal; "
                "print(callable(stage_creator_door_proposal))"
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


def test_staging_module_does_not_import_real_bridge_modules() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from engine.editor.creator_mode.creator_door_staging "
                "import stage_creator_door_proposal; "
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


def test_bridge_receives_mutation_safe_deepcopy() -> None:
    bridge = MutatingBridge()
    workflow = build_creator_door_workflow(_existing_door_request())
    before = _workflow_snapshot(workflow)

    result = stage_creator_door_proposal(workflow, bridge)

    assert result.ok is True
    assert _workflow_snapshot(workflow) == before


class FakeBridge:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, object]]] = []

    def stage_pending_proposal(self, ops: list[dict[str, object]]) -> dict[str, object]:
        self.calls.append(ops)
        return {
            "ok": True,
            "proposal_id": "proposal-1",
            "proposal": {
                "preview_summary": "Set SceneExit params on 'door_north'",
                "dry_run": {"ok": True},
            },
            "preview": "fallback preview",
            "warnings": [],
        }


class IdentityBridge:
    def __init__(self) -> None:
        self.ops: list[dict[str, object]] | None = None

    def stage_pending_proposal(self, ops: list[dict[str, object]]) -> dict[str, object]:
        self.ops = ops
        return {"ok": True, "proposal_id": "proposal-1", "preview": "ok"}


class FailureBridge:
    def stage_pending_proposal(self, ops: list[dict[str, object]]) -> dict[str, object]:
        return {"ok": False, "message": "dry-run failed"}


class ExceptionBridge:
    def stage_pending_proposal(self, ops: list[dict[str, object]]) -> dict[str, object]:
        raise RuntimeError("boom")


class PreviewOnlyBridge:
    def stage_pending_proposal(self, ops: list[dict[str, object]]) -> dict[str, object]:
        return {"ok": True, "proposal_id": "proposal-1", "preview": "Preview fallback"}


class WarningBridge:
    def stage_pending_proposal(self, ops: list[dict[str, object]]) -> dict[str, object]:
        return {
            "ok": True,
            "proposal_id": "proposal-1",
            "preview": "ok",
            "warnings": ["bridge warning"],
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


class MutatingBridge:
    def stage_pending_proposal(self, ops: list[dict[str, object]]) -> dict[str, object]:
        copied = copy.deepcopy(ops)
        ops[0]["entity_id"] = "mutated"
        params = ops[0].get("params")
        if isinstance(params, dict):
            params["target_scene"] = "mutated"
        return {"ok": True, "proposal_id": "proposal-1", "preview": str(copied)}


def _existing_door_request() -> CreatorDoorWorkflowRequest:
    return CreatorDoorWorkflowRequest(
        source_scene="forest",
        destination_scene="town",
        destination_spawn_id="north_gate_entry",
        source_entity_id="door_north",
    )


def _workflow_snapshot(workflow):
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
