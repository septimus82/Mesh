"""Editor scale operations for entity transform.

This module provides pure functions and dataclasses for entity scale
operations. Handles scale computation, snapping, command generation, and undo.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Any, Dict, Tuple


@dataclass(frozen=True, slots=True)
class ScaleEntityCommand:
    """Command representing an entity scale operation for undo/redo."""

    entity_id: str
    start_scale: float
    end_scale: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for undo stack."""
        return {
            "type": "ScaleEntity",
            "entity_id": self.entity_id,
            "before": self.start_scale,
            "after": self.end_scale,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScaleEntityCommand":
        """Create from dictionary format."""
        return cls(
            entity_id=str(data.get("entity_id", "")),
            start_scale=float(data.get("before", 1.0)),
            end_scale=float(data.get("after", 1.0)),
        )


@dataclass(frozen=True, slots=True)
class ScaleEntitiesCommand:
    """Command representing a group scale operation for undo/redo."""

    scales: Tuple[ScaleEntityCommand, ...]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for undo stack."""
        return {
            "type": "ScaleEntities",
            "scales": [s.to_dict() for s in self.scales],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScaleEntitiesCommand":
        """Create from dictionary format."""
        raw_scales = data.get("scales", [])
        scales = tuple(ScaleEntityCommand.from_dict(s) for s in raw_scales)
        return cls(scales=scales)


# Minimum scale to avoid zero/negative/inversion
MIN_SCALE = 0.05


def clamp_scale(x: float) -> float:
    """Clamp scale to minimum value.

    Args:
        x: Scale factor.

    Returns:
        Scale clamped to >= MIN_SCALE.
    """
    return max(MIN_SCALE, x)


def compute_scale_factor(
    pivot: Tuple[float, float],
    mouse_start: Tuple[float, float],
    mouse_now: Tuple[float, float],
) -> float:
    """Compute scale factor from mouse drag distances.

    Args:
        pivot: Pivot point (x, y).
        mouse_start: Mouse position at drag start.
        mouse_now: Current mouse position.

    Returns:
        Scale factor (dist_now / dist_start), with safe fallback to 1.0.
    """
    dx_start = mouse_start[0] - pivot[0]
    dy_start = mouse_start[1] - pivot[1]
    dist_start = math.sqrt(dx_start * dx_start + dy_start * dy_start)

    dx_now = mouse_now[0] - pivot[0]
    dy_now = mouse_now[1] - pivot[1]
    dist_now = math.sqrt(dx_now * dx_now + dy_now * dy_now)

    # Safe fallback when start distance is too small
    if dist_start < 1.0:
        return 1.0

    return dist_now / dist_start


def snap_scale_factor(f: float, step: float = 0.1) -> float:
    """Snap scale factor to nearest step.

    Args:
        f: Scale factor.
        step: Snap step.

    Returns:
        Snapped scale factor.
    """
    if step <= 0:
        return f
    return round(f / step) * step


def _find_entity_by_id(scene_json: Dict[str, Any], entity_id: str) -> Dict[str, Any] | None:
    """Find an entity in scene JSON by ID.

    Args:
        scene_json: Scene data dictionary.
        entity_id: Entity ID to find.

    Returns:
        Entity dict if found, None otherwise.
    """
    entities = scene_json.get("entities")
    if not isinstance(entities, list):
        return None

    key = str(entity_id or "").strip()

    # Handle index-based IDs
    if key.startswith("idx:"):
        try:
            idx = int(key.split(":", 1)[1])
        except Exception:  # noqa: BLE001  # REASON: malformed idx entity ids should fall back to the name-based scale lookup path
            idx = -1
        if 0 <= idx < len(entities) and isinstance(entities[idx], dict):
            found: dict[str, Any] = entities[idx]
            return found
        return None

    # Search by various ID fields
    for entity in entities:
        if not isinstance(entity, dict):
            continue
        for id_key in ("id", "entity_id", "mesh_name", "name"):
            raw = entity.get(id_key)
            if isinstance(raw, str) and raw.strip() == key:
                result: dict[str, Any] = entity
                return result
    return None


def _get_entity_scale(entity: Dict[str, Any]) -> float:
    """Get entity scale from component or legacy fields.

    Args:
        entity: Entity dictionary.

    Returns:
        Scale factor (default 1.0).
    """
    # Check components container first
    components = entity.get("components")
    if isinstance(components, dict):
        transform = components.get("transform")
        if isinstance(transform, dict):
            scale = transform.get("scale")
            if scale is not None:
                return float(scale)

    # Fallback to legacy fields
    for key in ("scale", "scale_factor"):
        val = entity.get(key)
        if val is not None:
            return float(val)

    return 1.0


def _set_entity_scale(entity: Dict[str, Any], scale: float) -> None:
    """Set entity scale in component or legacy fields.

    Mutates the entity dict in-place.

    Args:
        entity: Entity dictionary.
        scale: Scale factor.
    """
    # Clamp scale
    scale = clamp_scale(scale)

    # Check components container first
    components = entity.get("components")
    if isinstance(components, dict):
        transform = components.get("transform")
        if isinstance(transform, dict):
            transform["scale"] = scale
            return
        # Create transform if components exists but no transform
        components["transform"] = {"scale": scale}
        return

    # Check for legacy scale field
    if "scale" in entity:
        entity["scale"] = scale
        return
    if "scale_factor" in entity:
        entity["scale_factor"] = scale
        return

    # Default: use "scale" field
    entity["scale"] = scale


def apply_scale_entity(
    scene_json: Dict[str, Any],
    cmd: ScaleEntityCommand,
) -> Dict[str, Any]:
    """Apply a scale command to scene JSON, updating only the target entity.

    Args:
        scene_json: Scene data dictionary.
        cmd: Scale command to apply.

    Returns:
        Updated scene JSON (deep copy, input is not mutated).
    """
    result = copy.deepcopy(scene_json)
    entity = _find_entity_by_id(result, cmd.entity_id)
    if entity is not None:
        _set_entity_scale(entity, cmd.end_scale)
    return result


def apply_scale_entities(
    scene_json: Dict[str, Any],
    cmd: ScaleEntitiesCommand,
) -> Dict[str, Any]:
    """Apply a group scale command to scene JSON.

    Args:
        scene_json: Scene data dictionary.
        cmd: Group scale command to apply.

    Returns:
        Updated scene JSON (deep copy, input is not mutated).
    """
    result = copy.deepcopy(scene_json)
    for scale in cmd.scales:
        entity = _find_entity_by_id(result, scale.entity_id)
        if entity is not None:
            _set_entity_scale(entity, scale.end_scale)
    return result


def invert_scale_entity(cmd: ScaleEntityCommand) -> ScaleEntityCommand:
    """Create the inverse of a scale command (for undo).

    Args:
        cmd: Scale command to invert.

    Returns:
        New ScaleEntityCommand with start/end swapped.
    """
    return ScaleEntityCommand(
        entity_id=cmd.entity_id,
        start_scale=cmd.end_scale,
        end_scale=cmd.start_scale,
    )


def invert_scale_entities(cmd: ScaleEntitiesCommand) -> ScaleEntitiesCommand:
    """Create the inverse of a group scale command (for undo).

    Args:
        cmd: Group scale command to invert.

    Returns:
        New ScaleEntitiesCommand with all start/end swapped.
    """
    inverted = tuple(invert_scale_entity(s) for s in cmd.scales)
    return ScaleEntitiesCommand(scales=inverted)


def create_scale_entities_command_from_drag(
    start_scales: Dict[str, float],
    factor: float,
) -> ScaleEntitiesCommand | None:
    """Create a group scale command from drag factor.

    Args:
        start_scales: Dict mapping entity_id -> start scale.
        factor: Scale factor to apply.

    Returns:
        ScaleEntitiesCommand if factor is significant, None otherwise.
    """
    # Check if factor is ~1.0 within epsilon
    if abs(factor - 1.0) < 0.001:
        return None
    if not start_scales:
        return None

    # Sort entity IDs for stable ordering
    sorted_ids = sorted(start_scales.keys())
    scales = []
    for entity_id in sorted_ids:
        start_scale = start_scales[entity_id]
        end_scale = clamp_scale(start_scale * factor)
        scales.append(
            ScaleEntityCommand(
                entity_id=entity_id,
                start_scale=start_scale,
                end_scale=end_scale,
            )
        )

    return ScaleEntitiesCommand(scales=tuple(scales))


def get_entity_scale_from_scene(
    scene_json: Dict[str, Any],
    entity_id: str,
) -> float:
    """Get entity scale from scene JSON.

    Args:
        scene_json: Scene data dictionary.
        entity_id: Entity ID to find.

    Returns:
        Scale factor, or 1.0 if not found.
    """
    entity = _find_entity_by_id(scene_json, entity_id)
    if entity is None:
        return 1.0
    return _get_entity_scale(entity)
