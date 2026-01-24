"""Editor rotation operations for entity transform.

This module provides pure functions and dataclasses for entity rotation
operations. Handles angle computation, snapping, command generation, and undo.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Any, Dict, Tuple


@dataclass(frozen=True, slots=True)
class RotateEntityCommand:
    """Command representing an entity rotation operation for undo/redo."""

    entity_id: str
    start_rot_deg: float
    end_rot_deg: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for undo stack."""
        return {
            "type": "RotateEntity",
            "entity_id": self.entity_id,
            "before": self.start_rot_deg,
            "after": self.end_rot_deg,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RotateEntityCommand":
        """Create from dictionary format."""
        return cls(
            entity_id=str(data.get("entity_id", "")),
            start_rot_deg=float(data.get("before", 0.0)),
            end_rot_deg=float(data.get("after", 0.0)),
        )


@dataclass(frozen=True, slots=True)
class RotateEntitiesCommand:
    """Command representing a group rotation operation for undo/redo."""

    rotates: Tuple[RotateEntityCommand, ...]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for undo stack."""
        return {
            "type": "RotateEntities",
            "rotates": [r.to_dict() for r in self.rotates],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RotateEntitiesCommand":
        """Create from dictionary format."""
        raw_rotates = data.get("rotates", [])
        rotates = tuple(RotateEntityCommand.from_dict(r) for r in raw_rotates)
        return cls(rotates=rotates)


def wrap_deg(x: float) -> float:
    """Wrap angle to [0, 360) range.

    Args:
        x: Angle in degrees.

    Returns:
        Angle wrapped to [0, 360) range.
    """
    result = x % 360.0
    if result < 0:
        result += 360.0
    return result


def compute_angle_deg(px: float, py: float, mx: float, my: float) -> float:
    """Compute angle from pivot to mouse in degrees.

    Args:
        px: Pivot x coordinate.
        py: Pivot y coordinate.
        mx: Mouse x coordinate.
        my: Mouse y coordinate.

    Returns:
        Angle in degrees [0, 360).
    """
    dx = mx - px
    dy = my - py
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return 0.0
    angle_rad = math.atan2(dy, dx)
    angle_deg = math.degrees(angle_rad)
    return wrap_deg(angle_deg)


def compute_rotation_delta_deg(
    pivot: Tuple[float, float],
    mouse_start: Tuple[float, float],
    mouse_now: Tuple[float, float],
) -> float:
    """Compute rotation delta from mouse drag.

    Args:
        pivot: Pivot point (x, y).
        mouse_start: Mouse position at drag start.
        mouse_now: Current mouse position.

    Returns:
        Rotation delta in degrees, wrapped to [-180, 180].
    """
    angle_start = compute_angle_deg(pivot[0], pivot[1], mouse_start[0], mouse_start[1])
    angle_now = compute_angle_deg(pivot[0], pivot[1], mouse_now[0], mouse_now[1])
    delta = angle_now - angle_start
    # Wrap to [-180, 180]
    while delta > 180.0:
        delta -= 360.0
    while delta < -180.0:
        delta += 360.0
    return delta


def snap_rot_deg(x: float, step: float = 15.0) -> float:
    """Snap rotation to nearest step.

    Args:
        x: Angle in degrees.
        step: Snap step in degrees.

    Returns:
        Snapped angle.
    """
    if step <= 0:
        return x
    return round(x / step) * step


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
        except Exception:  # noqa: BLE001
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


def _get_entity_rotation(entity: Dict[str, Any]) -> float:
    """Get entity rotation from component or legacy fields.

    Args:
        entity: Entity dictionary.

    Returns:
        Rotation in degrees.
    """
    # Check components container first
    components = entity.get("components")
    if isinstance(components, dict):
        transform = components.get("transform")
        if isinstance(transform, dict):
            rot = transform.get("rotation")
            if rot is not None:
                return float(rot)

    # Fallback to legacy fields
    for key in ("rotation", "rotation_deg", "rot"):
        val = entity.get(key)
        if val is not None:
            return float(val)

    return 0.0


def _set_entity_rotation(entity: Dict[str, Any], rotation_deg: float) -> None:
    """Set entity rotation in component or legacy fields.

    Mutates the entity dict in-place.

    Args:
        entity: Entity dictionary.
        rotation_deg: Rotation in degrees.
    """
    # Wrap to [0, 360)
    rotation_deg = wrap_deg(rotation_deg)

    # Check components container first
    components = entity.get("components")
    if isinstance(components, dict):
        transform = components.get("transform")
        if isinstance(transform, dict):
            transform["rotation"] = rotation_deg
            return
        # Create transform if components exists but no transform
        components["transform"] = {"rotation": rotation_deg}
        return

    # Check for legacy rotation field
    if "rotation" in entity:
        entity["rotation"] = rotation_deg
        return
    if "rotation_deg" in entity:
        entity["rotation_deg"] = rotation_deg
        return

    # Default: use "rotation" field
    entity["rotation"] = rotation_deg


def apply_rotate_entity(
    scene_json: Dict[str, Any],
    cmd: RotateEntityCommand,
) -> Dict[str, Any]:
    """Apply a rotate command to scene JSON, updating only the target entity.

    Args:
        scene_json: Scene data dictionary.
        cmd: Rotate command to apply.

    Returns:
        Updated scene JSON (deep copy, input is not mutated).
    """
    result = copy.deepcopy(scene_json)
    entity = _find_entity_by_id(result, cmd.entity_id)
    if entity is not None:
        _set_entity_rotation(entity, cmd.end_rot_deg)
    return result


def apply_rotate_entities(
    scene_json: Dict[str, Any],
    cmd: RotateEntitiesCommand,
) -> Dict[str, Any]:
    """Apply a group rotate command to scene JSON.

    Args:
        scene_json: Scene data dictionary.
        cmd: Group rotate command to apply.

    Returns:
        Updated scene JSON (deep copy, input is not mutated).
    """
    result = copy.deepcopy(scene_json)
    for rotate in cmd.rotates:
        entity = _find_entity_by_id(result, rotate.entity_id)
        if entity is not None:
            _set_entity_rotation(entity, rotate.end_rot_deg)
    return result


def invert_rotate_entity(cmd: RotateEntityCommand) -> RotateEntityCommand:
    """Create the inverse of a rotate command (for undo).

    Args:
        cmd: Rotate command to invert.

    Returns:
        New RotateEntityCommand with start/end swapped.
    """
    return RotateEntityCommand(
        entity_id=cmd.entity_id,
        start_rot_deg=cmd.end_rot_deg,
        end_rot_deg=cmd.start_rot_deg,
    )


def invert_rotate_entities(cmd: RotateEntitiesCommand) -> RotateEntitiesCommand:
    """Create the inverse of a group rotate command (for undo).

    Args:
        cmd: Group rotate command to invert.

    Returns:
        New RotateEntitiesCommand with all start/end swapped.
    """
    inverted = tuple(invert_rotate_entity(r) for r in cmd.rotates)
    return RotateEntitiesCommand(rotates=inverted)


def create_rotate_entities_command_from_drag(
    start_rots: Dict[str, float],
    delta_deg: float,
) -> RotateEntitiesCommand | None:
    """Create a group rotate command from drag delta.

    Args:
        start_rots: Dict mapping entity_id -> start rotation in degrees.
        delta_deg: Rotation delta to apply.

    Returns:
        RotateEntitiesCommand if delta is significant, None otherwise.
    """
    if abs(delta_deg) < 0.01:
        return None
    if not start_rots:
        return None

    # Sort entity IDs for stable ordering
    sorted_ids = sorted(start_rots.keys())
    rotates = []
    for entity_id in sorted_ids:
        start_rot = start_rots[entity_id]
        end_rot = wrap_deg(start_rot + delta_deg)
        rotates.append(
            RotateEntityCommand(
                entity_id=entity_id,
                start_rot_deg=start_rot,
                end_rot_deg=end_rot,
            )
        )

    return RotateEntitiesCommand(rotates=tuple(rotates))


def get_entity_rotation_from_scene(
    scene_json: Dict[str, Any],
    entity_id: str,
) -> float:
    """Get entity rotation from scene JSON.

    Args:
        scene_json: Scene data dictionary.
        entity_id: Entity ID to find.

    Returns:
        Rotation in degrees, or 0.0 if not found.
    """
    entity = _find_entity_by_id(scene_json, entity_id)
    if entity is None:
        return 0.0
    return _get_entity_rotation(entity)
