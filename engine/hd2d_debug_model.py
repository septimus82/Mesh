"""Pure model for HD-2D depth debug formatting.

Provides deterministic, headless-safe functions for:
- Formatting render key info for sprites
- Summarizing HD-2D render state
- Generating debug overlay text
"""

from __future__ import annotations

from typing import Any, Sequence


def format_render_key_line(
    entity_id: str,
    render_layer: int,
    y_pos: float,
    depth_z: float,
    sort_mode: str = "y_sort",
) -> str:
    """Format a single render key debug line.

    Args:
        entity_id: Entity identifier
        render_layer: Coarse render layer
        y_pos: Y position for sorting
        depth_z: Explicit depth value
        sort_mode: 'y_sort' or 'explicit_z'

    Returns:
        Formatted debug line like "layer=0 y=100.0 z=0.0 id=player"
    """
    if sort_mode == "explicit_z":
        return f"layer={render_layer} z={depth_z:.1f} y={y_pos:.1f} id={entity_id}"
    return f"layer={render_layer} y={y_pos:.1f} id={entity_id}"


def extract_sprite_debug_info(sprite: Any) -> dict[str, Any]:
    """Extract debug info from a sprite for HD-2D display.

    Headless-safe: works with any object having the expected attributes.

    Args:
        sprite: Arcade sprite with optional mesh_entity_data

    Returns:
        Dict with entity_id, render_layer, y_pos, depth_z
    """
    entity_data = getattr(sprite, "mesh_entity_data", None) or {}

    entity_id = ""
    for key in ("id", "entity_id", "name", "mesh_name"):
        val = entity_data.get(key)
        if isinstance(val, str) and val.strip():
            entity_id = val.strip()
            break

    render_layer = 0
    rl = entity_data.get("render_layer")
    if rl is not None:
        try:
            render_layer = int(rl)
        except (TypeError, ValueError):
            pass

    depth_z = 0.0
    dz = entity_data.get("depth_z")
    if dz is not None:
        try:
            depth_z = float(dz)
        except (TypeError, ValueError):
            pass

    y_pos = 0.0
    cy = getattr(sprite, "center_y", None)
    if cy is not None:
        try:
            y_pos = float(cy)
        except (TypeError, ValueError):
            pass

    return {
        "entity_id": entity_id,
        "render_layer": render_layer,
        "y_pos": y_pos,
        "depth_z": depth_z,
    }


def format_hd2d_summary(
    sort_mode: str,
    sprite_count: int,
    plane_count: int,
) -> str:
    """Format HD-2D summary line.

    Args:
        sort_mode: 'y_sort' or 'explicit_z'
        sprite_count: Total sprites in render queue
        plane_count: Background plane count

    Returns:
        Formatted summary like "mode=y_sort sprites=42 planes=3"
    """
    return f"mode={sort_mode} sprites={sprite_count} planes={plane_count}"


def format_hd2d_debug_text(
    sort_mode: str,
    sprite_count: int,
    plane_count: int,
    sprite_infos: Sequence[dict[str, Any]],
    max_entries: int = 10,
) -> str:
    """Format full HD-2D debug overlay text.

    Args:
        sort_mode: 'y_sort' or 'explicit_z'
        sprite_count: Total sprites
        plane_count: Background plane count
        sprite_infos: Sequence of sprite debug info dicts (from extract_sprite_debug_info)
        max_entries: Maximum sprite entries to show

    Returns:
        Multi-line debug text for overlay display
    """
    lines = [
        "HD-2D Depth Debug",
        format_hd2d_summary(sort_mode, sprite_count, plane_count),
        "",
    ]

    if not sprite_infos:
        lines.append("(no sprites)")
        return "\n".join(lines)

    # Sort sprite infos deterministically for display
    sorted_infos = sort_sprite_infos_for_display(sprite_infos, sort_mode)

    shown = sorted_infos[:max_entries]
    for info in shown:
        line = format_render_key_line(
            entity_id=info.get("entity_id", ""),
            render_layer=info.get("render_layer", 0),
            y_pos=info.get("y_pos", 0.0),
            depth_z=info.get("depth_z", 0.0),
            sort_mode=sort_mode,
        )
        lines.append(line)

    remaining = len(sorted_infos) - len(shown)
    if remaining > 0:
        lines.append(f"... +{remaining} more")

    return "\n".join(lines)


def sort_sprite_infos_for_display(
    sprite_infos: Sequence[dict[str, Any]],
    sort_mode: str = "y_sort",
) -> list[dict[str, Any]]:
    """Sort sprite infos deterministically for display.

    Uses same ordering as render_sort_model to show front-to-back.

    Args:
        sprite_infos: Sequence of sprite debug info dicts
        sort_mode: 'y_sort' or 'explicit_z'

    Returns:
        New list sorted by render order (back to front)
    """
    def sort_key(info: dict[str, Any]) -> tuple[int, float, float, str]:
        render_layer = info.get("render_layer", 0)
        y_pos = info.get("y_pos", 0.0)
        depth_z = info.get("depth_z", 0.0)
        entity_id = info.get("entity_id", "")

        if sort_mode == "explicit_z":
            return (render_layer, depth_z, y_pos, entity_id)
        return (render_layer, y_pos, 0.0, entity_id)

    return sorted(sprite_infos, key=sort_key)


def compute_hd2d_debug_payload(
    sort_mode: str,
    sprites: Sequence[Any],
    plane_count: int,
) -> dict[str, Any]:
    """Compute HD-2D debug payload from sprites.

    Pure function: extracts info without side effects.

    Args:
        sort_mode: 'y_sort' or 'explicit_z'
        sprites: Sequence of arcade sprites
        plane_count: Background plane count

    Returns:
        Dict with sort_mode, sprite_count, plane_count, sprite_infos
    """
    sprite_infos = [extract_sprite_debug_info(s) for s in sprites]
    return {
        "sort_mode": sort_mode,
        "sprite_count": len(sprites),
        "plane_count": plane_count,
        "sprite_infos": sprite_infos,
    }
