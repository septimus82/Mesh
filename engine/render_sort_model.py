"""Pure model for deterministic render ordering.

Supports HD-2D rendering with:
- render_layer: coarse ordering (lower renders first / behind)
- depth_z: fine-grained depth within a layer (for explicit_z mode)
- y-sort: automatic depth by y-position (lower y = further back)

Sort modes:
- 'y_sort' (default): order by render_layer, then by -center_y (higher y drawn later)
- 'explicit_z': order by render_layer, then by depth_z
"""

from __future__ import annotations

from typing import Any, Tuple, Union

# Type alias for the sort key tuple
# y_sort: (render_layer, y_pos, entity_id)
# explicit_z: (render_layer, depth_z, y_pos, entity_id)
RenderSortKey = Union[Tuple[int, float, str], Tuple[int, float, float, str]]


def compute_render_sort_key(
    entity_dict: dict[str, Any],
    *,
    sort_mode: str = "y_sort",
) -> RenderSortKey:
    """Compute a deterministic sort key for render ordering.

    Args:
        entity_dict: Entity payload dict with optional render_layer, depth_z, y, center_y, id
        sort_mode: 'y_sort' (default) or 'explicit_z'

    Returns:
        Tuple (render_layer, depth_value, entity_id) for stable sorting.
        Lower tuple values render first (further back).
    """
    # Extract render_layer with default 0
    render_layer = _get_int(entity_dict, "render_layer", default=0)

    # Extract entity_id for tie-breaking (deterministic)
    entity_id = _get_entity_id(entity_dict)

    if sort_mode == "explicit_z":
        # Use depth_z directly; lower depth_z = further back
        # y_pos as secondary tie-breaker, then entity_id
        depth_z = _get_float(entity_dict, "depth_z", default=0.0)
        y_pos = _get_y_position(entity_dict)
        return (render_layer, depth_z, y_pos, entity_id)

    # y_sort mode (default): use y position
    # Convention: lower y = further back (renders first), higher y = closer (renders last)
    # This matches typical 2D top-down or isometric games where higher y = foreground
    y_pos = _get_y_position(entity_dict)
    return (render_layer, y_pos, entity_id)


def sort_entities_for_render(
    entities: list[dict[str, Any]],
    *,
    sort_mode: str = "y_sort",
) -> list[dict[str, Any]]:
    """Sort entity dicts by render order (stable, deterministic).

    Args:
        entities: List of entity payload dicts
        sort_mode: 'y_sort' (default) or 'explicit_z'

    Returns:
        New list sorted by render order (first = back, last = front).
    """
    return sorted(
        entities,
        key=lambda e: compute_render_sort_key(e, sort_mode=sort_mode),
    )


def compute_sprite_render_sort_key(
    sprite: Any,
    *,
    sort_mode: str = "y_sort",
) -> RenderSortKey:
    """Compute render sort key from a sprite with mesh_entity_data.

    Args:
        sprite: Arcade sprite with optional mesh_entity_data attribute
        sort_mode: 'y_sort' (default) or 'explicit_z'

    Returns:
        Tuple (render_layer, depth_value, entity_id) for stable sorting.
    """
    entity_data = getattr(sprite, "mesh_entity_data", None) or {}

    # Extract render_layer
    render_layer = _get_int(entity_data, "render_layer", default=0)

    # Extract entity_id
    entity_id = _get_entity_id(entity_data)

    if sort_mode == "explicit_z":
        depth_z = _get_float(entity_data, "depth_z", default=0.0)
        # Get y position for secondary tie-breaking
        y_pos = getattr(sprite, "center_y", None)
        if y_pos is None:
            y_pos = _get_y_position(entity_data)
        else:
            y_pos = float(y_pos)
        return (render_layer, depth_z, y_pos, entity_id)

    # y_sort mode: use sprite's center_y if available
    # Lower y = renders first (back), higher y = renders last (front)
    y_pos = getattr(sprite, "center_y", None)
    if y_pos is None:
        y_pos = _get_y_position(entity_data)
    else:
        y_pos = float(y_pos)

    return (render_layer, y_pos, entity_id)


def sort_sprites_for_render(
    sprites: list[Any],
    *,
    sort_mode: str = "y_sort",
) -> list[Any]:
    """Sort sprites by render order (stable, deterministic).

    Args:
        sprites: List of Arcade sprites with optional mesh_entity_data
        sort_mode: 'y_sort' (default) or 'explicit_z'

    Returns:
        New list sorted by render order (first = back, last = front).
    """
    return sorted(
        sprites,
        key=lambda s: compute_sprite_render_sort_key(s, sort_mode=sort_mode),
    )


# -----------------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------------


def _get_int(data: dict[str, Any], key: str, *, default: int) -> int:
    """Safely extract an int value from dict."""
    value = data.get(key)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _get_float(data: dict[str, Any], key: str, *, default: float) -> float:
    """Safely extract a float value from dict."""
    value = data.get(key)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _get_entity_id(data: dict[str, Any]) -> str:
    """Extract entity id for tie-breaking, with fallback."""
    for key in ("id", "entity_id", "name", "mesh_name"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    # Fallback to empty string for determinism
    return ""


def _get_y_position(data: dict[str, Any]) -> float:
    """Extract y position from entity dict."""
    # Try center_y first, then y
    for key in ("center_y", "y"):
        value = data.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    return 0.0
