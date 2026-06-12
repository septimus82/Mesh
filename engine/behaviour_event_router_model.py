"""
Pure model for routing system events (e.g. sensors) to behaviours.

Deterministic, testable, and decoupled from runtime execution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Literal, Optional, Tuple

from .sensors_model import SensorDef, SensorEvent


@dataclass(frozen=True)
class BehaviourEvent:
    """A standardized event for behaviours."""
    kind: str  # e.g. "sensor_enter", "sensor_exit"
    entity_id: str | None
    sensor_id: str
    tags: Tuple[str, ...] = field(default_factory=tuple)
    scene_path: Optional[str] = None
    target_entity_id: str | None = None
    origin: Literal["player", "entity", "scene", "unknown"] = "unknown"

@dataclass(frozen=True)
class DispatchTarget:
    """Instruction on where to send an event."""
    kind: str  # "entity" or "scene"
    target_id: str  # entity_id or scene identifier
    handler_name: str

@dataclass(frozen=True)
class DispatchPlan:
    """Deterministic plan for dispatching a behaviour event."""
    handler_name: str
    entity_target_id: str | None
    resolved_entity_target_id: str | None
    entity_handler_enabled: bool
    scene_target_enabled: bool
    allow_primary_fallback: bool

def handler_name_for_event(kind: str) -> str:
    """Map event kind to handler method name."""
    if kind == "sensor_enter":
        return "on_sensor_enter"
    if kind == "sensor_exit":
        return "on_sensor_exit"
    return f"on_{kind}"

def build_sensor_behaviour_events(
    sensor_events: Tuple[SensorEvent, ...],
    sensors: Tuple[SensorDef, ...],
    scene_path: Optional[str] = None,
    *,
    origin: Literal["player", "entity", "scene", "unknown"] = "unknown",
) -> Tuple[BehaviourEvent, ...]:
    """
    Convert raw sensor events into behaviour events, enriching with tags.
    Sorts events deterministically: enter before exit? 
    Actually, usually exit before enter is safer for state transitions (leave old before enter new).
    But the Sensors Model might have already sorted them.
    Sensors Model `diff_overlaps` returns exits then enters. We should preserve that order.
    """
    sensor_map = {s.id: s for s in sensors}
    result = []

    for se in sensor_events:
        sensor = sensor_map.get(se.sensor_id)
        tags = sensor.tags if sensor else ()

        # event.kind is "enter" or "exit" from sensors_model
        # BehaviourEvent.kind -> "sensor_enter" or "sensor_exit"
        evt_kind = f"sensor_{se.kind}"

        result.append(BehaviourEvent(
            kind=evt_kind,
            entity_id=se.entity_id,
            sensor_id=se.sensor_id,
            tags=tags,
            scene_path=scene_path,
            target_entity_id=se.entity_id,
            origin=origin,
        ))

    return tuple(result)

def should_fallback_to_primary(event: BehaviourEvent) -> bool:
    if event.origin == "player":
        return True
    return "primary_player" in event.tags

def compute_dispatch_targets(
    event: BehaviourEvent,
    entity_behaviours_index: Dict[str, Tuple[str, ...]],
    scene_behaviours_index: Tuple[str, ...],
    *,
    resolved_entity_id: str | None = None,
) -> DispatchPlan:
    """
    Determine which targets should receive this event and whether to
    attempt primary-player fallback when the entity cannot be resolved.
    """
    handler = handler_name_for_event(event.kind)
    target_id = event.target_entity_id if event.target_entity_id is not None else event.entity_id
    effective_id = resolved_entity_id if resolved_entity_id is not None else target_id
    entity_methods = entity_behaviours_index.get(effective_id, ()) if effective_id else ()
    entity_handler_enabled = handler in entity_methods
    scene_target_enabled = handler in scene_behaviours_index
    allow_primary_fallback = should_fallback_to_primary(event)
    resolved_entity_target_id = effective_id if entity_handler_enabled else None
    return DispatchPlan(
        handler_name=handler,
        entity_target_id=target_id,
        resolved_entity_target_id=resolved_entity_target_id,
        entity_handler_enabled=entity_handler_enabled,
        scene_target_enabled=scene_target_enabled,
        allow_primary_fallback=allow_primary_fallback,
    )
