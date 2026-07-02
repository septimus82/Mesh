"""Pure Creator Mode door workflow to live-op adapter."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .creator_door_plan import CreatorDoorPlanOperation
from .creator_door_workflow import CreatorDoorWorkflowModel

_SUPPORTED_PLAN_OPS = frozenset(
    {"ensure_door_entity", "configure_scene_exit", "configure_lock"}
)
_CANNOT_REPRESENT = "Door workflow cannot be represented by current live ops."


@dataclass(frozen=True, slots=True)
class CreatorDoorLiveOpsResult:
    """Read-only conversion result for existing live-op proposal dictionaries."""

    ok: bool
    ops: tuple[dict[str, object], ...]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def build_creator_door_live_ops(
    workflow: CreatorDoorWorkflowModel,
) -> CreatorDoorLiveOpsResult:
    """Convert a door workflow into existing live-op dictionaries when safe."""

    warnings = tuple(workflow.plan.warnings)
    if not workflow.plan.ok:
        return CreatorDoorLiveOpsResult(
            ok=False,
            ops=(),
            errors=("Door workflow is blocked.", *tuple(workflow.plan.errors)),
            warnings=warnings,
        )

    unsupported = _unsupported_operations(workflow.plan.operations)
    if unsupported:
        return CreatorDoorLiveOpsResult(
            ok=False,
            ops=(),
            errors=tuple(f"Unsupported door plan operation: {op}." for op in unsupported),
            warnings=warnings,
        )

    payload = _first_payload(workflow.plan.operations)
    source_entity_id = _text(payload, "source_entity_id")
    if not source_entity_id:
        return CreatorDoorLiveOpsResult(
            ok=False,
            ops=(),
            errors=(_CANNOT_REPRESENT,),
            warnings=warnings,
        )

    if not any(operation.op == "configure_scene_exit" for operation in workflow.plan.operations):
        return CreatorDoorLiveOpsResult(
            ok=False,
            ops=(),
            errors=(_CANNOT_REPRESENT,),
            warnings=warnings,
        )

    params: dict[str, object] = {
        "target_scene": _text(payload, "destination_scene"),
        "target_spawn": _text(payload, "destination_spawn_id"),
        "trigger": _text(payload, "trigger") or "interact",
    }
    if any(operation.op == "configure_lock" for operation in workflow.plan.operations):
        params["locked"] = bool(payload.get("locked"))
        params["requires_flag"] = _text(payload, "required_flag")

    op: dict[str, object] = {
        "type": "set_behaviour_params",
        "scene_path": _text(payload, "source_scene"),
        "entity_id": source_entity_id,
        "behaviour_name": "SceneExit",
        "params": dict(params),
    }
    return CreatorDoorLiveOpsResult(
        ok=True,
        ops=(op,),
        errors=(),
        warnings=warnings,
    )


def _unsupported_operations(
    operations: tuple[CreatorDoorPlanOperation, ...]
) -> tuple[str, ...]:
    unsupported: list[str] = []
    for operation in operations:
        op_name = str(operation.op or "").strip()
        if op_name not in _SUPPORTED_PLAN_OPS:
            unsupported.append(op_name or "unknown")
    return tuple(unsupported)


def _first_payload(
    operations: tuple[CreatorDoorPlanOperation, ...]
) -> Mapping[str, object]:
    for operation in operations:
        if isinstance(operation.payload, Mapping):
            return operation.payload
    return {}


def _text(payload: Mapping[str, object], key: str) -> str:
    return str(payload.get(key) or "").strip()
