"""Pure model for batch applying HD-2D overrides to multiple entities.

Provides functions to:
- List entities with their positions from scene payload
- Select entities within radius of a center entity
- Select entities with same render_layer as center entity
- Compute deterministic batch apply targets
"""

from __future__ import annotations

import math
from typing import Any, Literal

# =============================================================================
# Entity Position Extraction
# =============================================================================


def list_entities_with_positions(
    scene_payload: dict[str, Any],
) -> list[tuple[str, float, float, str | None, float | None]]:
    """Extract entity positions and metadata from scene payload.

    Args:
        scene_payload: The scene payload dict.

    Returns:
        List of tuples: (entity_id, x, y, render_layer, depth_z)
        Entities missing required fields are skipped.
        Results are sorted by entity_id for determinism.
    """
    if not isinstance(scene_payload, dict):
        return []

    entities = scene_payload.get("entities")
    if not entities:
        return []

    result: list[tuple[str, float, float, str | None, float | None]] = []

    # Handle both list and dict entity storage
    if isinstance(entities, list):
        for ent in entities:
            if not isinstance(ent, dict):
                continue
            entity_id = ent.get("id") or ent.get("mesh_name")
            if not entity_id:
                continue
            # Skip entities without position
            x = ent.get("x")
            y = ent.get("y")
            if x is None or y is None:
                continue
            try:
                x_f = float(x)
                y_f = float(y)
            except (TypeError, ValueError):
                continue
            render_layer = ent.get("render_layer")
            depth_z = ent.get("depth_z")
            if depth_z is not None:
                try:
                    depth_z = float(depth_z)
                except (TypeError, ValueError):
                    depth_z = None
            result.append((str(entity_id), x_f, y_f, render_layer, depth_z))
    elif isinstance(entities, dict):
        for entity_id, ent in entities.items():
            if not isinstance(ent, dict):
                continue
            x = ent.get("x")
            y = ent.get("y")
            if x is None or y is None:
                continue
            try:
                x_f = float(x)
                y_f = float(y)
            except (TypeError, ValueError):
                continue
            render_layer = ent.get("render_layer")
            depth_z = ent.get("depth_z")
            if depth_z is not None:
                try:
                    depth_z = float(depth_z)
                except (TypeError, ValueError):
                    depth_z = None
            result.append((str(entity_id), x_f, y_f, render_layer, depth_z))

    # Sort by entity_id for determinism
    result.sort(key=lambda t: t[0])
    return result


# =============================================================================
# Target Selection Functions
# =============================================================================


def select_entities_in_radius(
    center_id: str,
    radius_px: float,
    entities: list[tuple[str, float, float, str | None, float | None]],
    include_center: bool = True,
) -> list[str]:
    """Select entities within radius of center entity.

    Args:
        center_id: The entity ID to use as center.
        radius_px: The radius in pixels.
        entities: List from list_entities_with_positions().
        include_center: Whether to include the center entity in results.

    Returns:
        Sorted list of entity IDs within radius.
    """
    if radius_px < 0:
        return []

    # Find center entity position
    center_pos: tuple[float, float] | None = None
    for eid, x, y, _layer, _depth in entities:
        if eid == center_id:
            center_pos = (x, y)
            break

    if center_pos is None:
        return []

    cx, cy = center_pos
    result: list[str] = []

    for eid, x, y, _layer, _depth in entities:
        if eid == center_id:
            if include_center:
                result.append(eid)
            continue
        # Euclidean distance
        dist = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
        if dist <= radius_px:
            result.append(eid)

    # Sort for determinism
    result.sort()
    return result


def select_entities_same_render_layer(
    center_id: str,
    entities: list[tuple[str, float, float, str | None, float | None]],
    include_center: bool = True,
) -> list[str]:
    """Select entities with same render_layer as center entity.

    Args:
        center_id: The entity ID to use as reference.
        entities: List from list_entities_with_positions().
        include_center: Whether to include the center entity in results.

    Returns:
        Sorted list of entity IDs with matching render_layer.
    """
    # Find center entity's render_layer
    center_layer: str | None = None
    found = False
    for eid, _x, _y, layer, _depth in entities:
        if eid == center_id:
            center_layer = layer
            found = True
            break

    if not found:
        return []

    result: list[str] = []

    for eid, _x, _y, layer, _depth in entities:
        if eid == center_id:
            if include_center:
                result.append(eid)
            continue
        # Match layer (None matches None)
        if layer == center_layer:
            result.append(eid)

    # Sort for determinism
    result.sort()
    return result


def compute_batch_apply_targets(
    scene_payload: dict[str, Any],
    center_id: str,
    mode: Literal["radius", "layer"],
    radius_px: float = 96.0,
    include_center: bool = True,
) -> list[str]:
    """Compute deterministic batch apply targets.

    Args:
        scene_payload: The scene payload dict.
        center_id: The center entity ID.
        mode: Selection mode - "radius" or "layer".
        radius_px: Radius in pixels (only used for "radius" mode).
        include_center: Whether to include the center entity.

    Returns:
        Sorted list of target entity IDs.
    """
    entities = list_entities_with_positions(scene_payload)

    if mode == "radius":
        return select_entities_in_radius(center_id, radius_px, entities, include_center)
    elif mode == "layer":
        return select_entities_same_render_layer(center_id, entities, include_center)
    else:
        return []
