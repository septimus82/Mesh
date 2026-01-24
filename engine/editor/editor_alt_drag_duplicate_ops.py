"""Alt-Drag Duplicate operations for the editor.

This module provides pure helper functions for alt-drag duplication.
All functions are deterministic and headless-safe (no Arcade dependency).
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Literal


# -----------------------------------------------------------------------------
# Data Models
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class DuplicateEntitySpec:
    """Specification for a single duplicated entity.

    Attributes:
        src_id: Original entity ID
        new_id: New entity ID for the duplicate
        entity_json: Deep copy of source entity data
        start_xy: Initial position (at duplicate creation)
        end_xy: Final position (after drag)
    """

    src_id: str
    new_id: str
    entity_json: dict[str, Any]
    start_xy: tuple[float, float]
    end_xy: tuple[float, float]


@dataclass(frozen=True)
class AltDragDuplicateCommand:
    """Command representing an alt-drag duplicate operation.

    This is a single undoable command that duplicates entities
    and moves them to their final positions.

    Attributes:
        kind: Command type identifier
        specs: Tuple of duplicate specifications
        pivot_src_id: Source ID of the pivot entity (for snapping)
        pivot_new_id: New ID of the pivot entity
        snap_enabled: Whether snapping was enabled
        snap_mode: Snap mode (grid8/grid16/tile_center)
    """

    kind: Literal["alt_drag_duplicate"] = "alt_drag_duplicate"
    specs: tuple[DuplicateEntitySpec, ...] = field(default_factory=tuple)
    pivot_src_id: str | None = None
    pivot_new_id: str | None = None
    snap_enabled: bool = False
    snap_mode: str = "grid16"

    def to_dict(self) -> dict[str, Any]:
        """Convert command to dictionary for undo stack serialization."""
        return {
            "type": "AltDragDuplicate",
            "kind": self.kind,
            "specs": [
                {
                    "src_id": spec.src_id,
                    "new_id": spec.new_id,
                    "entity_json": spec.entity_json,
                    "start_xy": list(spec.start_xy),
                    "end_xy": list(spec.end_xy),
                }
                for spec in self.specs
            ],
            "pivot_src_id": self.pivot_src_id,
            "pivot_new_id": self.pivot_new_id,
            "snap_enabled": self.snap_enabled,
            "snap_mode": self.snap_mode,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AltDragDuplicateCommand":
        """Reconstruct command from dictionary."""
        specs_data = data.get("specs", [])
        specs = tuple(
            DuplicateEntitySpec(
                src_id=str(s.get("src_id", "")),
                new_id=str(s.get("new_id", "")),
                entity_json=dict(s.get("entity_json", {})),
                start_xy=(float(s.get("start_xy", (0.0, 0.0))[0]), float(s.get("start_xy", (0.0, 0.0))[1])),
                end_xy=(float(s.get("end_xy", (0.0, 0.0))[0]), float(s.get("end_xy", (0.0, 0.0))[1])),
            )
            for s in specs_data
        )
        return cls(
            kind="alt_drag_duplicate",
            specs=specs,
            pivot_src_id=data.get("pivot_src_id"),
            pivot_new_id=data.get("pivot_new_id"),
            snap_enabled=bool(data.get("snap_enabled", False)),
            snap_mode=str(data.get("snap_mode", "grid16")),
        )


# -----------------------------------------------------------------------------
# Pure Functions
# -----------------------------------------------------------------------------


def normalize_selection_ids(selected_ids: list[str]) -> list[str]:
    """Return a deterministically sorted list of entity IDs.

    Args:
        selected_ids: List of selected entity IDs.

    Returns:
        Sorted list of entity IDs (alphabetical).
    """
    return sorted(selected_ids)


def compute_next_copy_ids(
    scene_entities: list[dict[str, Any]],
    base_ids: list[str],
) -> dict[str, str]:
    """Compute unique copy IDs for a list of source entity IDs.

    ID pattern: <base>_copy_1, _copy_2, etc.
    Scans existing entity IDs to find next available numbers.

    Args:
        scene_entities: List of existing entity dictionaries in the scene.
        base_ids: List of source entity IDs to generate copies for.

    Returns:
        Dict mapping source ID to new copy ID.
    """
    # Collect all existing entity IDs
    existing_ids: set[str] = set()
    for entity in scene_entities:
        if isinstance(entity, dict):
            for key in ("id", "entity_id", "mesh_name", "name"):
                eid = entity.get(key)
                if isinstance(eid, str) and eid.strip():
                    existing_ids.add(eid.strip())
                    break

    result: dict[str, str] = {}

    for src_id in base_ids:
        # Strip any existing _copy_N suffix to get base name
        base_match = re.match(r"^(.+?)(?:_copy(?:_\d+)?)?$", src_id)
        base = base_match.group(1) if base_match else src_id

        # Find max existing copy number for this base
        copy_pattern = re.compile(rf"^{re.escape(base)}_copy(?:_(\d+))?$")
        max_num = 0

        for eid in existing_ids:
            match = copy_pattern.match(eid)
            if match:
                num_str = match.group(1)
                if num_str is None:
                    max_num = max(max_num, 1)
                else:
                    max_num = max(max_num, int(num_str))

        # Generate next ID
        next_num = max_num + 1
        new_id = f"{base}_copy_{next_num}"

        # Add to existing to prevent conflicts within this batch
        existing_ids.add(new_id)
        result[src_id] = new_id

    return result


def _get_entity_id(entity: dict[str, Any]) -> str | None:
    """Extract entity ID from entity data."""
    for key in ("id", "entity_id", "mesh_name", "name"):
        eid = entity.get(key)
        if isinstance(eid, str) and eid.strip():
            return eid.strip()
    return None


def _get_entity_position(entity: dict[str, Any]) -> tuple[float, float]:
    """Extract position from entity data."""
    x = float(entity.get("x", 0.0))
    y = float(entity.get("y", 0.0))
    return (x, y)


def duplicate_entities_in_scene(
    scene_json: dict[str, Any],
    selected_ids: list[str],
) -> tuple[dict[str, Any], list[DuplicateEntitySpec]]:
    """Duplicate selected entities in the scene.

    Creates deep copies of selected entities with new IDs.
    All fields are kept identical except the ID.

    Args:
        scene_json: Scene data dictionary.
        selected_ids: List of entity IDs to duplicate.

    Returns:
        Tuple of (new_scene_json, specs) where specs has start=end=original positions.
    """
    # Get existing entities
    entities = scene_json.get("entities", [])
    if not isinstance(entities, list):
        entities = []

    # Normalize IDs for deterministic ordering
    sorted_ids = normalize_selection_ids(selected_ids)

    # Compute new IDs
    id_map = compute_next_copy_ids(entities, sorted_ids)

    # Find and duplicate entities
    specs: list[DuplicateEntitySpec] = []
    new_entities: list[dict[str, Any]] = []

    for src_id in sorted_ids:
        new_id = id_map.get(src_id)
        if not new_id:
            continue

        # Find source entity
        src_entity: dict[str, Any] | None = None
        for entity in entities:
            if _get_entity_id(entity) == src_id:
                src_entity = entity
                break

        if src_entity is None:
            continue

        # Deep copy entity
        new_entity = copy.deepcopy(src_entity)

        # Update ID fields
        if "id" in new_entity:
            new_entity["id"] = new_id
        if "entity_id" in new_entity:
            new_entity["entity_id"] = new_id
        if "name" in new_entity:
            new_entity["name"] = new_id
        if "mesh_name" in new_entity:
            new_entity["mesh_name"] = new_id

        # Ensure at least one ID field exists
        if not any(k in new_entity for k in ("id", "entity_id", "name", "mesh_name")):
            new_entity["name"] = new_id

        pos = _get_entity_position(new_entity)
        spec = DuplicateEntitySpec(
            src_id=src_id,
            new_id=new_id,
            entity_json=new_entity,
            start_xy=pos,
            end_xy=pos,
        )
        specs.append(spec)
        new_entities.append(new_entity)

    # Create new scene with duplicated entities appended
    new_scene = copy.deepcopy(scene_json)
    if "entities" not in new_scene:
        new_scene["entities"] = []
    new_scene["entities"].extend(new_entities)

    return new_scene, specs


def apply_drag_delta_to_specs(
    specs: list[DuplicateEntitySpec] | tuple[DuplicateEntitySpec, ...],
    delta_xy: tuple[float, float],
    snap_enabled: bool,
    snap_mode: str,
    tile_size_px: int | None,
    pivot_new_id: str | None,
) -> list[DuplicateEntitySpec]:
    """Apply drag delta to duplicate specs, snapping only the pivot.

    The pivot entity's position is snapped, then the snapped delta
    is applied uniformly to all other entities.

    Args:
        specs: List of duplicate specifications.
        delta_xy: Raw drag delta (world coordinates).
        snap_enabled: Whether snapping is enabled.
        snap_mode: Snap mode (grid8/grid16/tile_center).
        tile_size_px: Tile size for tile_center mode.
        pivot_new_id: ID of the pivot entity (for snapping).

    Returns:
        New list of specs with updated end_xy positions.
    """
    from engine.editor_light_occluder_ops import snap_world_point  # noqa: PLC0415

    if not specs:
        return []

    # Find pivot spec
    pivot_spec: DuplicateEntitySpec | None = None
    for spec in specs:
        if spec.new_id == pivot_new_id:
            pivot_spec = spec
            break

    if pivot_spec is None and specs:
        pivot_spec = specs[0]

    # Compute pivot's raw end position
    pivot_start = pivot_spec.start_xy if pivot_spec else (0.0, 0.0)
    pivot_raw_end = (pivot_start[0] + delta_xy[0], pivot_start[1] + delta_xy[1])

    # Snap pivot position if enabled
    if snap_enabled:
        pivot_snapped_end = snap_world_point(pivot_raw_end, snap_mode, tile_size_px)
    else:
        pivot_snapped_end = pivot_raw_end

    # Compute snapped delta
    snapped_delta = (
        pivot_snapped_end[0] - pivot_start[0],
        pivot_snapped_end[1] - pivot_start[1],
    )

    # Apply snapped delta to all specs
    result: list[DuplicateEntitySpec] = []
    for spec in specs:
        new_end = (
            spec.start_xy[0] + snapped_delta[0],
            spec.start_xy[1] + snapped_delta[1],
        )
        result.append(
            DuplicateEntitySpec(
                src_id=spec.src_id,
                new_id=spec.new_id,
                entity_json=spec.entity_json,
                start_xy=spec.start_xy,
                end_xy=new_end,
            )
        )

    return result


def apply_alt_drag_duplicate(
    scene_json: dict[str, Any],
    cmd: AltDragDuplicateCommand,
) -> dict[str, Any]:
    """Apply an alt-drag duplicate command to the scene.

    Adds duplicated entities (if not already present) and sets
    their positions to cmd.specs[*].end_xy.

    Args:
        scene_json: Scene data dictionary.
        cmd: The alt-drag duplicate command.

    Returns:
        New scene dictionary with duplicates added/positioned.
    """
    new_scene = copy.deepcopy(scene_json)
    entities = new_scene.get("entities", [])
    if not isinstance(entities, list):
        entities = []
        new_scene["entities"] = entities

    # Build map of existing entity IDs
    existing_ids: set[str] = set()
    for entity in entities:
        eid = _get_entity_id(entity)
        if eid:
            existing_ids.add(eid)

    # Add/update duplicated entities
    for spec in cmd.specs:
        if spec.new_id in existing_ids:
            # Update position of existing entity
            for entity in entities:
                if _get_entity_id(entity) == spec.new_id:
                    entity["x"] = spec.end_xy[0]
                    entity["y"] = spec.end_xy[1]
                    break
        else:
            # Add new entity with end position
            new_entity = copy.deepcopy(spec.entity_json)
            new_entity["x"] = spec.end_xy[0]
            new_entity["y"] = spec.end_xy[1]
            entities.append(new_entity)
            existing_ids.add(spec.new_id)

    return new_scene


def remove_alt_drag_duplicates(
    scene_json: dict[str, Any],
    cmd: AltDragDuplicateCommand,
) -> dict[str, Any]:
    """Remove duplicated entities from the scene (for undo).

    Args:
        scene_json: Scene data dictionary.
        cmd: The alt-drag duplicate command.

    Returns:
        New scene dictionary with duplicates removed.
    """
    new_scene = copy.deepcopy(scene_json)
    entities = new_scene.get("entities", [])
    if not isinstance(entities, list):
        return new_scene

    # Collect IDs to remove
    ids_to_remove = {spec.new_id for spec in cmd.specs}

    # Filter out duplicates
    new_entities = [
        entity
        for entity in entities
        if _get_entity_id(entity) not in ids_to_remove
    ]

    new_scene["entities"] = new_entities
    return new_scene


def should_start_alt_drag_duplicate(
    clicked_entity_id: str | None,
    selected_ids: list[str],
    alt_held: bool,
    editor_mode_active: bool,
    gizmo_active: bool,
) -> bool:
    """Determine if alt-drag duplicate should start.

    Args:
        clicked_entity_id: ID of clicked entity (None if empty space).
        selected_ids: Currently selected entity IDs.
        alt_held: Whether Alt modifier is held.
        editor_mode_active: Whether editor mode is active.
        gizmo_active: Whether a gizmo operation is active.

    Returns:
        True if alt-drag duplicate should start.
    """
    if not editor_mode_active:
        return False
    if not alt_held:
        return False
    if gizmo_active:
        return False
    if not clicked_entity_id:
        return False
    if not selected_ids:
        return False
    if clicked_entity_id not in selected_ids:
        return False
    return True
