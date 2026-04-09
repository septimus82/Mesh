"""Editor transform operations for entity movement.

This module provides pure functions and dataclasses for entity transform
operations (move/drag). Handles snapping, command generation, and undo.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

# Import snap function from existing module
from engine.editor_light_occluder_ops import snap_world_point


@dataclass(frozen=True, slots=True)
class MoveEntityCommand:
    """Command representing an entity move operation for undo/redo."""
    entity_id: str
    start_xy: Tuple[float, float]
    end_xy: Tuple[float, float]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for undo stack."""
        return {
            "type": "MoveEntity",
            "entity_name": self.entity_id,
            "before": {"x": self.start_xy[0], "y": self.start_xy[1]},
            "after": {"x": self.end_xy[0], "y": self.end_xy[1]},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MoveEntityCommand":
        """Create from dictionary format."""
        before = data.get("before", {})
        after = data.get("after", {})
        return cls(
            entity_id=str(data.get("entity_id", data.get("entity_name", ""))),
            start_xy=(float(before.get("x", 0.0)), float(before.get("y", 0.0))),
            end_xy=(float(after.get("x", 0.0)), float(after.get("y", 0.0))),
        )


@dataclass(frozen=True, slots=True)
class MoveEntitiesCommand:
    """Command representing a group move operation for undo/redo."""

    moves: Tuple[MoveEntityCommand, ...]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format for undo stack."""
        return {
            "type": "MoveEntities",
            "moves": [m.to_dict() for m in self.moves],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MoveEntitiesCommand":
        """Create from dictionary format."""
        raw_moves = data.get("moves", [])
        moves = tuple(MoveEntityCommand.from_dict(m) for m in raw_moves)
        return cls(moves=moves)


def compute_dragged_xy(
    entity_start_xy: Tuple[float, float],
    drag_start_mouse_xy: Tuple[float, float],
    current_mouse_xy: Tuple[float, float],
) -> Tuple[float, float]:
    """Compute new entity position from drag deltas.

    Args:
        entity_start_xy: Entity position when drag started.
        drag_start_mouse_xy: Mouse world position when drag started.
        current_mouse_xy: Current mouse world position.

    Returns:
        New entity (x, y) position.
    """
    dx = current_mouse_xy[0] - drag_start_mouse_xy[0]
    dy = current_mouse_xy[1] - drag_start_mouse_xy[1]
    return (entity_start_xy[0] + dx, entity_start_xy[1] + dy)


def apply_snap_to_xy(
    xy: Tuple[float, float],
    snap_enabled: bool,
    snap_mode: str,
    tile_size: int = 16,
) -> Tuple[float, float]:
    """Apply snapping to a position.

    Args:
        xy: Position to snap.
        snap_enabled: Whether snapping is enabled.
        snap_mode: Snap mode ("grid8", "grid16", "tile_center", or "none").
        tile_size: Tile size in pixels for tile_center mode.

    Returns:
        Snapped (x, y) position.
    """
    if not snap_enabled:
        return xy
    return snap_world_point(xy, snap_mode, tile_size)


def apply_move_command(
    scene_json: Dict[str, Any],
    cmd: MoveEntityCommand,
) -> Dict[str, Any]:
    """Apply a move command to scene JSON, updating only the target entity.

    Args:
        scene_json: Scene data dictionary.
        cmd: Move command to apply.

    Returns:
        Updated scene JSON (deep copy, input is not mutated).
    """
    result = copy.deepcopy(scene_json)
    entity = _find_entity_by_id(result, cmd.entity_id)
    if entity is not None:
        entity["x"] = cmd.end_xy[0]
        entity["y"] = cmd.end_xy[1]
    return result


def invert_move_command(cmd: MoveEntityCommand) -> MoveEntityCommand:
    """Create the inverse of a move command (for undo).

    Args:
        cmd: Move command to invert.

    Returns:
        New MoveEntityCommand with start/end swapped.
    """
    return MoveEntityCommand(
        entity_id=cmd.entity_id,
        start_xy=cmd.end_xy,
        end_xy=cmd.start_xy,
    )


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
        except Exception:  # noqa: BLE001  # REASON: malformed idx entity ids should fall back to the name-based transform lookup path
            idx = -1
        if 0 <= idx < len(entities) and isinstance(entities[idx], dict):
            idx_entity: Dict[str, Any] = entities[idx]
            return idx_entity
        return None

    # Search by various ID fields
    for idx, entity in enumerate(entities):
        if not isinstance(entity, dict):
            continue
        # Check standard ID fields
        for id_key in ("id", "entity_id", "mesh_name", "name"):
            raw = entity.get(id_key)
            if isinstance(raw, str) and raw.strip() == key:
                result: Dict[str, Any] = entity
                return result
    return None


def resolve_entity_id_for_sprite(sprite: Any, fallback_index: int | None = None) -> str | None:
    """Resolve the entity ID from a sprite object.

    Args:
        sprite: The sprite object.
        fallback_index: Index to use as fallback ID.

    Returns:
        Entity ID string, or None if not resolvable.
    """
    if sprite is None:
        return None

    # Try mesh_entity_data first
    entity_data = getattr(sprite, "mesh_entity_data", None)
    if isinstance(entity_data, dict):
        for key in ("id", "entity_id"):
            raw = entity_data.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
        mesh_name = entity_data.get("mesh_name")
        if isinstance(mesh_name, str) and mesh_name.strip():
            return mesh_name.strip()
        name = entity_data.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()

    # Try direct sprite attributes
    mesh_name = getattr(sprite, "mesh_name", None)
    if isinstance(mesh_name, str) and mesh_name.strip():
        return mesh_name.strip()

    name = getattr(sprite, "name", None)
    if isinstance(name, str) and name.strip():
        return name.strip()

    # Use fallback index
    if fallback_index is not None:
        return f"idx:{int(fallback_index)}"

    return None


def create_move_command_from_drag(
    entity_id: str,
    start_pos: Tuple[float, float],
    end_pos: Tuple[float, float],
) -> MoveEntityCommand | None:
    """Create a move command from drag start/end positions.

    Only creates a command if the position actually changed.

    Args:
        entity_id: ID of the entity being moved.
        start_pos: Starting position.
        end_pos: Ending position.

    Returns:
        MoveEntityCommand if position changed, None otherwise.
    """
    if not entity_id:
        return None
    if start_pos == end_pos:
        return None
    return MoveEntityCommand(
        entity_id=entity_id,
        start_xy=start_pos,
        end_xy=end_pos,
    )


def apply_group_move_command(
    scene_json: Dict[str, Any],
    cmd: MoveEntitiesCommand,
) -> Dict[str, Any]:
    """Apply a group move command to scene JSON.

    Args:
        scene_json: Scene data dictionary.
        cmd: Group move command to apply.

    Returns:
        Updated scene JSON (deep copy, input is not mutated).
    """
    result = copy.deepcopy(scene_json)
    for move in cmd.moves:
        entity = _find_entity_by_id(result, move.entity_id)
        if entity is not None:
            entity["x"] = move.end_xy[0]
            entity["y"] = move.end_xy[1]
    return result


def invert_group_move_command(cmd: MoveEntitiesCommand) -> MoveEntitiesCommand:
    """Create the inverse of a group move command (for undo).

    Args:
        cmd: Group move command to invert.

    Returns:
        New MoveEntitiesCommand with all start/end swapped.
    """
    inverted_moves = tuple(invert_move_command(m) for m in cmd.moves)
    return MoveEntitiesCommand(moves=inverted_moves)


def create_group_move_command_from_drag(
    entity_start_positions: List[Tuple[str, Tuple[float, float]]],
    delta: Tuple[float, float],
) -> MoveEntitiesCommand | None:
    """Create a group move command from drag delta.

    Args:
        entity_start_positions: List of (entity_id, start_xy) tuples.
        delta: (dx, dy) movement delta to apply.

    Returns:
        MoveEntitiesCommand if delta is non-zero, None otherwise.
    """
    if delta == (0.0, 0.0):
        return None
    if not entity_start_positions:
        return None

    moves: List[MoveEntityCommand] = []
    for entity_id, start_xy in entity_start_positions:
        end_xy = (start_xy[0] + delta[0], start_xy[1] + delta[1])
        moves.append(MoveEntityCommand(entity_id=entity_id, start_xy=start_xy, end_xy=end_xy))

    return MoveEntitiesCommand(moves=tuple(moves))
