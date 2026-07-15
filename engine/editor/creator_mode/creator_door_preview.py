"""Pure Creator Mode door plan preview models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .creator_door_plan import CreatorDoorPlan, CreatorDoorPlanOperation

_STAGE_DISABLED_REASON = "Proposal staging is not available in this slice."
_APPLY_DISABLED_REASON = "Creator Mode cannot apply door plans yet."


@dataclass(frozen=True, slots=True)
class CreatorDoorPreviewStep:
    """One friendly read-only explanation of a planned operation."""

    title: str
    detail: str
    severity: str = "info"


@dataclass(frozen=True, slots=True)
class CreatorDoorPreviewAction:
    """A disabled future action shown for preview only."""

    label: str
    enabled: bool
    reason: str = ""


@dataclass(frozen=True, slots=True)
class CreatorDoorPreviewModel:
    """UI-ready read-only preview for a door plan."""

    title: str
    summary: str
    status: str
    steps: tuple[CreatorDoorPreviewStep, ...]
    actions: tuple[CreatorDoorPreviewAction, ...]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def build_creator_door_preview(plan: CreatorDoorPlan) -> CreatorDoorPreviewModel:
    """Build a friendly preview model from a pure door plan."""

    if not plan.ok:
        return CreatorDoorPreviewModel(
            title=str(plan.title),
            summary="Fix the listed problems before this door can be planned.",
            status="blocked",
            steps=(),
            actions=_disabled_actions(),
            errors=tuple(plan.errors),
            warnings=tuple(plan.warnings),
        )

    return CreatorDoorPreviewModel(
        title=str(plan.title),
        summary=str(plan.summary),
        status="ready",
        steps=tuple(_step_for_operation(operation) for operation in plan.operations),
        actions=_disabled_actions(),
        errors=tuple(plan.errors),
        warnings=tuple(plan.warnings),
    )


def _disabled_actions() -> tuple[CreatorDoorPreviewAction, ...]:
    return (
        CreatorDoorPreviewAction(
            label="Stage Proposal",
            enabled=False,
            reason=_STAGE_DISABLED_REASON,
        ),
        CreatorDoorPreviewAction(
            label="Apply Changes",
            enabled=False,
            reason=_APPLY_DISABLED_REASON,
        ),
    )


def _step_for_operation(operation: CreatorDoorPlanOperation) -> CreatorDoorPreviewStep:
    if operation.op == "ensure_door_entity":
        target = _target_label(operation.target)
        return CreatorDoorPreviewStep(
            title="Prepare door",
            detail=f"Prepare {target} in the source map.",
        )
    if operation.op in {"configure_door_transition", "configure_scene_exit"}:
        payload = operation.payload
        destination = _friendly_destination(_payload_text(payload, "destination_scene")) or "the destination map"
        spawn = _payload_text(payload, "destination_spawn_id")
        trigger = _friendly_trigger(_payload_text(payload, "trigger") or "interact")
        lines = [f"Destination: {destination}."]
        if spawn:
            lines.append(f"Arrival point: {spawn}.")
        lines.append(f"Use: {trigger}.")
        return CreatorDoorPreviewStep(title="Configure selected door", detail=" ".join(lines))
    if operation.op == "configure_lock":
        required_flag = _payload_text(operation.payload, "required_flag") or "a required flag"
        return CreatorDoorPreviewStep(
            title="Set lock",
            detail=f"Keep the door locked until {required_flag} is set.",
        )
    return CreatorDoorPreviewStep(
        title="Plan step",
        detail=f"Review planned operation {str(operation.op or '').strip() or 'unknown'}.",
    )


def _target_label(target: str) -> str:
    clean = str(target or "").strip()
    return clean if clean else "new door"


def _payload_text(payload: Mapping[str, object], key: str) -> str:
    return str(payload.get(key) or "").strip()


def _friendly_destination(value: str) -> str:
    clean = str(value or "").strip().replace("\\", "/")
    if clean.startswith("scenes/"):
        clean = clean.removeprefix("scenes/")
    if clean.endswith(".json"):
        clean = clean.removesuffix(".json")
    return clean.replace("_", " ").replace("-", " ").title()


def _friendly_trigger(value: str) -> str:
    clean = str(value or "").strip()
    if not clean:
        return ""
    return clean.replace("_", " ").replace("-", " ").title()
