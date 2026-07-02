"""Read-only Creator Mode door staging readiness model."""

from __future__ import annotations

from dataclasses import dataclass

from .creator_door_live_ops import build_creator_door_live_ops
from .creator_door_workflow import CreatorDoorWorkflowModel

_STAGE_LABEL = "Stage Proposal"
_BRIDGE_UNAVAILABLE = "Proposal bridge is unavailable."


@dataclass(frozen=True, slots=True)
class CreatorDoorStagingReadinessAction:
    """One future UI action exposed by the read-only readiness model."""

    label: str
    enabled: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class CreatorDoorStagingReadinessModel:
    """Read-only status for whether a door workflow could be staged later."""

    status: str
    summary: str
    actions: tuple[CreatorDoorStagingReadinessAction, ...]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    live_ops_preview: tuple[str, ...]


def build_creator_door_staging_readiness(
    workflow: CreatorDoorWorkflowModel,
    bridge: object,
) -> CreatorDoorStagingReadinessModel:
    """Report whether a door workflow is stageable without staging it."""

    live_ops = build_creator_door_live_ops(workflow)
    if not live_ops.ok:
        reason = live_ops.errors[0] if live_ops.errors else "Door workflow is not stageable."
        return CreatorDoorStagingReadinessModel(
            status="blocked",
            summary="This door proposal cannot be staged yet.",
            actions=(_action(False, reason),),
            errors=tuple(live_ops.errors),
            warnings=tuple(live_ops.warnings),
            live_ops_preview=(),
        )

    preview = tuple(_preview_live_op(op) for op in live_ops.ops)
    stage = getattr(bridge, "stage_pending_proposal", None)
    if not callable(stage):
        return CreatorDoorStagingReadinessModel(
            status="bridge_unavailable",
            summary="The proposal bridge is not available.",
            actions=(_action(False, _BRIDGE_UNAVAILABLE),),
            errors=(_BRIDGE_UNAVAILABLE,),
            warnings=tuple(live_ops.warnings),
            live_ops_preview=preview,
        )

    return CreatorDoorStagingReadinessModel(
        status="ready",
        summary="This door proposal is ready to stage.",
        actions=(_action(True, ""),),
        errors=(),
        warnings=tuple(live_ops.warnings),
        live_ops_preview=preview,
    )


def _action(enabled: bool, reason: str) -> CreatorDoorStagingReadinessAction:
    return CreatorDoorStagingReadinessAction(
        label=_STAGE_LABEL,
        enabled=enabled,
        reason=reason,
    )


def _preview_live_op(op: dict[str, object]) -> str:
    op_type = _text(op.get("type"))
    if op_type == "set_behaviour_params":
        behaviour_name = _text(op.get("behaviour_name") or op.get("behaviour"))
        entity_id = _text(
            op.get("entity_id")
            or op.get("entity_name")
            or op.get("entity")
            or op.get("name")
            or op.get("id")
        )
        if behaviour_name and entity_id:
            return f"Set {behaviour_name} params on {entity_id}."
        if behaviour_name:
            return f"Set {behaviour_name} params."
        return "Set behaviour params."
    return f"Live op: {op_type or 'unknown'}"


def _text(value: object) -> str:
    return str(value or "").strip()
