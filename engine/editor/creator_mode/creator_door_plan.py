"""Pure Creator Mode door operation planning."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

_ALLOWED_TRIGGERS = frozenset({"interact", "touch", "auto"})
_DESTINATION_SPAWN_WARNING = "Door has no destination spawn point."


@dataclass(frozen=True, slots=True)
class CreatorDoorPlanRequest:
    """Friendly door creation/configuration intent."""

    source_scene: str
    destination_scene: str
    destination_spawn_id: str = ""
    door_name: str = ""
    source_entity_id: str = ""
    locked: bool = False
    required_flag: str = ""
    trigger: str = "interact"


@dataclass(frozen=True, slots=True)
class CreatorDoorPlanOperation:
    """One abstract operation that may later become an editor command."""

    op: str
    target: str
    payload: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class CreatorDoorPlan:
    """Read-only result for a proposed door operation plan."""

    ok: bool
    title: str
    summary: str
    operations: tuple[CreatorDoorPlanOperation, ...]
    errors: tuple[str, ...]
    warnings: tuple[str, ...]


def build_creator_door_plan(request: CreatorDoorPlanRequest) -> CreatorDoorPlan:
    """Build a deterministic, read-only door operation plan."""

    normalized = _normalize_request(request)
    errors = _validate(normalized)
    warnings = _warnings(normalized) if not errors else ()

    title = _title(normalized)
    if errors:
        return CreatorDoorPlan(
            ok=False,
            title=title,
            summary="Door plan is not ready.",
            operations=(),
            errors=errors,
            warnings=warnings,
        )

    operations = (
        _operation("ensure_door_entity", normalized["source_entity_id"], normalized),
        _operation("configure_scene_exit", normalized["source_entity_id"], normalized),
    )
    if normalized["locked"]:
        operations += (_operation("configure_lock", normalized["source_entity_id"], normalized),)

    return CreatorDoorPlan(
        ok=True,
        title=title,
        summary=_summary(normalized),
        operations=operations,
        errors=(),
        warnings=warnings,
    )


def _normalize_request(request: CreatorDoorPlanRequest) -> dict[str, object]:
    trigger = _clean(request.trigger) or "interact"
    return {
        "source_scene": _clean(request.source_scene),
        "destination_scene": _clean(request.destination_scene),
        "destination_spawn_id": _clean(request.destination_spawn_id),
        "door_name": _clean(request.door_name),
        "source_entity_id": _clean(request.source_entity_id),
        "locked": bool(request.locked),
        "required_flag": _clean(request.required_flag),
        "trigger": trigger,
    }


def _validate(normalized: Mapping[str, object]) -> tuple[str, ...]:
    errors: list[str] = []
    if not normalized["source_scene"]:
        errors.append("Source scene is required.")
    if not normalized["destination_scene"]:
        errors.append("Destination scene is required.")
    if normalized["trigger"] not in _ALLOWED_TRIGGERS:
        errors.append("Trigger must be one of: interact, touch, auto.")
    if bool(normalized["locked"]) and not normalized["required_flag"]:
        errors.append("Locked doors require a required flag.")
    return tuple(errors)


def _warnings(normalized: Mapping[str, object]) -> tuple[str, ...]:
    if not normalized["destination_spawn_id"]:
        return (_DESTINATION_SPAWN_WARNING,)
    return ()


def _operation(
    op: str,
    target: object,
    normalized: Mapping[str, object],
) -> CreatorDoorPlanOperation:
    return CreatorDoorPlanOperation(
        op=op,
        target=str(target or ""),
        payload=MappingProxyType(dict(normalized)),
    )


def _title(normalized: Mapping[str, object]) -> str:
    door_name = str(normalized["door_name"] or "").strip()
    if door_name:
        return f"Door plan: {door_name}"
    return "Door plan"


def _summary(normalized: Mapping[str, object]) -> str:
    source = str(normalized["source_scene"])
    destination = str(normalized["destination_scene"])
    spawn = str(normalized["destination_spawn_id"])
    if spawn:
        return f"Plan door from {source} to {destination} at {spawn}."
    return f"Plan door from {source} to {destination}."


def _clean(value: object) -> str:
    return str(value or "").strip()
