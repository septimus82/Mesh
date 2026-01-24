"""Clipboard operations for the editor.

This module provides pure helper functions for copy/paste operations
on entities. All functions are deterministic and headless-safe.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Tuple


def generate_copy_entity_id(existing_ids: List[str], source_id: str) -> str:
    """Generate a unique ID for a copied entity.

    Uses the pattern: <base>_copy_1, _copy_2, etc.
    Scans existing IDs to find the next available number.

    Args:
        existing_ids: List of existing entity IDs in the scene.
        source_id: The ID of the source entity being copied.

    Returns:
        A unique entity ID for the copy.
    """
    # Strip any existing _copy_N suffix to get base name
    base_match = re.match(r"^(.+?)(?:_copy(?:_\d+)?)?$", source_id)
    base = base_match.group(1) if base_match else source_id

    # Find all existing copy numbers for this base
    copy_pattern = re.compile(rf"^{re.escape(base)}_copy(?:_(\d+))?$")
    max_num = 0

    for eid in existing_ids:
        match = copy_pattern.match(eid)
        if match:
            num_str = match.group(1)
            if num_str is None:
                # _copy without number is treated as _copy_1
                max_num = max(max_num, 1)
            else:
                max_num = max(max_num, int(num_str))

    # Generate next ID
    next_num = max_num + 1
    return f"{base}_copy_{next_num}"


def clone_entity_payload(
    entity: Dict[str, Any],
    new_id: str,
    world_xy: Tuple[float, float],
) -> Dict[str, Any]:
    """Create a deep copy of an entity with a new ID and position.

    Args:
        entity: The source entity data dictionary.
        new_id: The new unique ID for the cloned entity.
        world_xy: The (x, y) world position for the new entity.

    Returns:
        A new entity dictionary with updated ID and position.
    """
    # Deep copy to avoid mutations
    new_entity = copy.deepcopy(entity)

    # Update position
    new_entity["x"] = float(world_xy[0])
    new_entity["y"] = float(world_xy[1])

    # Update ID fields - use the same key that was in the source
    # Priority: id > entity_id > name
    if "id" in new_entity:
        new_entity["id"] = new_id
    if "entity_id" in new_entity:
        new_entity["entity_id"] = new_id
    if "name" in new_entity:
        new_entity["name"] = new_id

    # If none of those exist, add "name"
    if "id" not in new_entity and "entity_id" not in new_entity and "name" not in new_entity:
        new_entity["name"] = new_id

    return new_entity


def get_entity_id_from_data(entity_data: Dict[str, Any]) -> str:
    """Extract the entity ID from entity data.

    Tries keys in order: id, entity_id, mesh_name, name.

    Args:
        entity_data: Entity data dictionary.

    Returns:
        The entity ID, or "unnamed" if not found.
    """
    for key in ("id", "entity_id", "mesh_name", "name"):
        raw = entity_data.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return "unnamed"


def collect_existing_entity_ids(sprites: Any) -> List[str]:
    """Collect all entity IDs from a list of sprites.

    Args:
        sprites: Iterable of sprites with mesh_entity_data attribute.

    Returns:
        List of entity IDs (deterministic order).
    """
    ids: List[str] = []
    for sprite in sprites:
        entity_data = getattr(sprite, "mesh_entity_data", None)
        if isinstance(entity_data, dict):
            eid = get_entity_id_from_data(entity_data)
            if eid and eid != "unnamed":
                ids.append(eid)
    return ids
