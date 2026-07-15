"""Pure Creator Mode door workflow to live-op adapter."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .creator_door_plan import CreatorDoorPlanOperation
from .creator_door_workflow import CreatorDoorWorkflowModel

_SUPPORTED_PLAN_OPS = frozenset(
    {"ensure_door_entity", "configure_door_transition", "configure_scene_exit", "configure_lock"}
)
_CANNOT_REPRESENT = "Door workflow cannot be represented by current live ops."
_LEGACY_INTERACT_ERROR = (
    "This legacy door is not wired to an interaction event. "
    "Use Advanced Mode or migrate it to SceneTransition."
)


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

    if not any(operation.op in {"configure_door_transition", "configure_scene_exit"} for operation in workflow.plan.operations):
        return CreatorDoorLiveOpsResult(
            ok=False,
            ops=(),
            errors=(_CANNOT_REPRESENT,),
            warnings=warnings,
        )

    if bool(payload.get("locked")):
        required_flag = _text(payload, "required_flag")
        if required_flag not in _strings(payload.get("entity_require_flags")):
            return CreatorDoorLiveOpsResult(
                ok=False,
                ops=(),
                errors=("Locked Creator doors require an existing entity flag gate.",),
                warnings=warnings,
            )

    behaviour_name = _text(payload, "transition_behaviour")
    params_result = _transition_params(payload, behaviour_name)
    if params_result[0] is None:
        return CreatorDoorLiveOpsResult(
            ok=False,
            ops=(),
            errors=(params_result[1] or _CANNOT_REPRESENT,),
            warnings=warnings,
        )
    params = params_result[0]

    if any(operation.op == "configure_lock" for operation in workflow.plan.operations):
        # Existing entity-level flag gates are preserved by leaving the gate untouched.
        params = dict(params)

    op: dict[str, object] = {
        "type": "set_behaviour_params",
        "scene_path": _text(payload, "source_scene"),
        "entity_id": source_entity_id,
        "behaviour_name": behaviour_name,
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


def _transition_params(
    payload: Mapping[str, object],
    behaviour_name: str,
) -> tuple[dict[str, object] | None, str]:
    trigger = _text(payload, "trigger") or "interact"
    target_scene = _text(payload, "destination_scene")
    spawn_id = _text(payload, "destination_spawn_id")

    if behaviour_name == "SceneTransition":
        if trigger == "auto":
            return None, "Automatic Creator doors are not representable by SceneTransition."
        if trigger == "touch":
            return {
                "target_scene": target_scene,
                "spawn_id": spawn_id,
                "allow_interact": False,
                "trigger_on_touch": True,
                "target_tag": "player",
            }, ""
        return {
            "target_scene": target_scene,
            "spawn_id": spawn_id,
            "allow_interact": True,
            "trigger_on_touch": False,
        }, ""

    if behaviour_name == "SceneExit":
        if trigger != "interact":
            return None, _LEGACY_INTERACT_ERROR
        listen_event = _text(payload, "scene_exit_listen_event") or "use_exit"
        if _text(payload, "interactable_event") != listen_event:
            return None, _LEGACY_INTERACT_ERROR
        return {
            "target_scene": target_scene,
            "target_spawn": spawn_id,
            "listen_event": listen_event,
        }, ""

    return None, "Selected door has no attached transition behaviour."


def _strings(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        clean = value.strip()
        return (clean,) if clean else ()
    if isinstance(value, Sequence):
        return tuple(str(item).strip() for item in value if str(item or "").strip())
    return ()
