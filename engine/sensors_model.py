"""
Pure model for sensor/trigger logic.

Deterministic, data-driven, and decoupled from runtime/rendering.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Mapping, Tuple

from .physics_model import Aabb


@dataclass(frozen=True)
class SensorDef:
    """Definition of a sensor zone."""
    id: str
    aabb: Aabb
    tags: Tuple[str, ...] = field(default_factory=tuple)
    enabled: bool = True

@dataclass(frozen=True)
class SensorEvent:
    """Event generated when an entity interacts with a sensor."""
    sensor_id: str
    entity_id: str
    kind: str  # "enter" or "exit"

def parse_sensors(scene_payload: Mapping[str, object]) -> Tuple[SensorDef, ...]:
    """
    Parse sensors from scene data.
    
    Expected format in value["sensors"]:
    [
        {"id": "zone_1", "rect": [x, y, w, h], "tags": ["trap"], "enabled": true},
        ...
    ]
    """
    raw_sensors = scene_payload.get("sensors", [])
    if not isinstance(raw_sensors, list) or not raw_sensors:
        return ()

    parsed: list[SensorDef] = []
    for s in raw_sensors:
        if not isinstance(s, dict):
            continue
        sid = str(s.get("id", ""))
        if not sid:
            continue

        rect_data = s.get("rect")
        if not isinstance(rect_data, list) or len(rect_data) != 4:
            continue

        x, y, w, h = rect_data
        aabb = Aabb(float(x), float(y), float(w), float(h))

        raw_tags = s.get("tags", [])
        if isinstance(raw_tags, list):
            tags = tuple(sorted(str(t) for t in raw_tags))
        else:
            tags = ()
        enabled = bool(s.get("enabled", True))

        parsed.append(SensorDef(sid, aabb, tags, enabled))

    # Sort by ID for stability
    parsed.sort(key=lambda x: x.id)
    return tuple(parsed)

def overlaps_for_entity(entity_aabb: Aabb, sensors: Tuple[SensorDef, ...]) -> Tuple[str, ...]:
    """
    Return sorted tuple of sensor IDs that the entity overlaps.
    """
    hits: list[str] = []
    for s in sensors:
        if not s.enabled:
            continue
        if s.aabb.intersection(entity_aabb):
            hits.append(s.id)
    return tuple(hits) # sensors are already sorted by ID, so iteration order is stable?
                       # Yes, but strictly speaking intersection doesn't guarantee output order
                       # unless we rely on input order. Since sensors is sorted, hits will be sorted.

def diff_overlaps(
    entity_id: str,
    prev_ids: Tuple[str, ...],
    next_ids: Tuple[str, ...]
) -> Tuple[SensorEvent, ...]:
    """
    Compare previous overlaps with current overlaps to generate enter/exit events.
    
    Order:
    1. EXITS (sorted by sensor ID)
    2. ENTERS (sorted by sensor ID)
    """
    prev_set = set(prev_ids)
    next_set = set(next_ids)

    exited = sorted(list(prev_set - next_set))
    entered = sorted(list(next_set - prev_set))

    events: List[SensorEvent] = []

    for sensor_id in exited:
        events.append(SensorEvent(sensor_id, entity_id, "exit"))

    for sensor_id in entered:
        events.append(SensorEvent(sensor_id, entity_id, "enter"))

    return tuple(events)
