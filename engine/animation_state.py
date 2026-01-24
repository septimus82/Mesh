"""Helpers for coordinating animation_state writes across behaviours."""

from __future__ import annotations

from typing import Any, Dict

BASE_PRIORITY = -1000.0


def _get_entity_data(entity: Any) -> dict[str, Any] | None:
    data = getattr(entity, "mesh_entity_data", None)
    if isinstance(data, dict):
        return data
    return None


def _meta(data: dict[str, Any]) -> dict[str, Any]:
    meta = data.get("_animation_state_meta")
    if not isinstance(meta, dict):
        meta = {"priority": BASE_PRIORITY, "timer": 0.0}
        data["_animation_state_meta"] = meta
    if "priority" not in meta:
        meta["priority"] = BASE_PRIORITY
    if "timer" not in meta:
        meta["timer"] = 0.0
    return meta


def request_animation_state(
    entity: Any,
    state: str,
    *,
    priority: float = 0.0,
    ttl: float = 0.0,
) -> bool:
    """Attempt to set the entity's animation_state with a priority override."""

    if not isinstance(state, str) or not state:
        return False

    data = _get_entity_data(entity)
    if data is None:
        return False

    meta = _meta(data)
    current_priority = float(meta.get("priority", BASE_PRIORITY))
    if priority < current_priority:
        return False

    data["animation_state"] = state
    meta["priority"] = float(priority)
    meta["timer"] = max(0.0, float(ttl))
    return True


def tick_animation_state(entity: Any, dt: float) -> None:
    """Decay any active override timers so lower priorities can take over."""

    data = _get_entity_data(entity)
    if data is None:
        return

    meta = data.get("_animation_state_meta")
    if not isinstance(meta, dict):
        return

    timer = float(meta.get("timer", 0.0))
    if timer <= 0.0:
        return

    timer = max(0.0, timer - max(0.0, float(dt)))
    meta["timer"] = timer
    if timer == 0.0:
        meta["priority"] = BASE_PRIORITY


def clear_animation_override(entity: Any) -> None:
    """Reset any priority override immediately."""

    data = _get_entity_data(entity)
    if data is None:
        return
    meta = data.get("_animation_state_meta")
    if isinstance(meta, dict):
        meta["priority"] = BASE_PRIORITY
        meta["timer"] = 0.0


def get_animation_state_snapshot(entity: Any) -> Dict[str, Any]:
    """Return a debug-friendly view of movement + animation state metadata."""

    data = _get_entity_data(entity) or {}
    snapshot: Dict[str, Any] = {
        "movement_state": data.get("movement_state"),
        "animation_state": data.get("animation_state"),
        "default_animation": data.get("default_animation"),
    }

    meta = data.get("_animation_state_meta")
    if isinstance(meta, dict):
        snapshot["priority"] = float(meta.get("priority", BASE_PRIORITY))
        snapshot["timer"] = max(0.0, float(meta.get("timer", 0.0)))
    else:
        snapshot["priority"] = BASE_PRIORITY
        snapshot["timer"] = 0.0

    snapshot["override_active"] = snapshot["timer"] > 0.0 and snapshot["priority"] > BASE_PRIORITY
    return snapshot
