"""Pure model for background plane editing operations.

Provides deterministic, side-effect-free functions for:
- Listing background planes (sorted by render_layer, id)
- Adding new planes with deterministic ID generation
- Duplicating existing planes
- Removing planes
- Updating plane fields with sanitization
- Reordering planes (move up/down)

All functions operate on scene payload dicts and return new payloads.
Import-safe and headless-safe (no Arcade/GL required).
"""

from __future__ import annotations

import copy
from typing import Any, Optional, Tuple

from engine.parallax_model import (
    BackgroundPlane,
    background_planes_to_payloads,
    parse_background_planes,
    sort_background_planes,
)


def list_background_planes(scene_payload: dict[str, Any]) -> list[BackgroundPlane]:
    """List background planes from scene payload, sorted deterministically.

    Args:
        scene_payload: Scene JSON dict

    Returns:
        List of BackgroundPlane objects sorted by (render_layer, id).
    """
    return parse_background_planes(scene_payload)


def add_background_plane(
    scene_payload: dict[str, Any],
    template: Optional[dict[str, Any]] = None,
) -> Tuple[dict[str, Any], str]:
    """Add a new background plane to the scene.

    Args:
        scene_payload: Scene JSON dict
        template: Optional template dict with initial field values

    Returns:
        Tuple of (new_scene_payload, new_plane_id).
    """
    new_payload = copy.deepcopy(scene_payload)

    # Ensure background_planes list exists
    if "background_planes" not in new_payload:
        new_payload["background_planes"] = []
    if not isinstance(new_payload["background_planes"], list):
        new_payload["background_planes"] = []

    # Collect existing IDs
    existing_ids = _collect_existing_ids(new_payload["background_planes"])

    # Generate deterministic unique ID
    new_id = _generate_unique_id(existing_ids, prefix="plane")

    # Build new plane entry
    new_entry: dict[str, Any] = {
        "id": new_id,
        "asset_path": "",
        "parallax": 0.5,
        "render_layer": 0,
        "alpha": 1.0,
        "offset_x": 0.0,
        "offset_y": 0.0,
        "repeat_x": False,
        "repeat_y": False,
    }

    # Apply template values if provided
    if template:
        for key in (
            "asset_path", "parallax", "render_layer", "alpha",
            "offset_x", "offset_y", "repeat_x", "repeat_y", "tint",
        ):
            if key in template:
                new_entry[key] = template[key]

    new_payload["background_planes"].append(new_entry)
    return new_payload, new_id


def duplicate_background_plane(
    scene_payload: dict[str, Any],
    plane_id: str,
) -> Tuple[dict[str, Any], str]:
    """Duplicate an existing background plane.

    Args:
        scene_payload: Scene JSON dict
        plane_id: ID of the plane to duplicate

    Returns:
        Tuple of (new_scene_payload, new_plane_id).
        If plane_id not found, returns (original_payload, "").
    """
    new_payload = copy.deepcopy(scene_payload)

    planes = new_payload.get("background_planes", [])
    if not isinstance(planes, list):
        return scene_payload, ""

    # Find source plane
    source_entry: dict[str, Any] | None = None
    for entry in planes:
        if isinstance(entry, dict) and entry.get("id") == plane_id:
            source_entry = entry
            break

    if source_entry is None:
        return scene_payload, ""

    # Collect existing IDs
    existing_ids = _collect_existing_ids(planes)

    # Generate new ID based on source
    base_id = f"{plane_id}_copy"
    new_id = _generate_unique_id(existing_ids, prefix=base_id)

    # Clone entry with new ID
    new_entry = copy.deepcopy(source_entry)
    new_entry["id"] = new_id

    new_payload["background_planes"].append(new_entry)
    return new_payload, new_id


def remove_background_plane(
    scene_payload: dict[str, Any],
    plane_id: str,
) -> dict[str, Any]:
    """Remove a background plane from the scene.

    Args:
        scene_payload: Scene JSON dict
        plane_id: ID of the plane to remove

    Returns:
        New scene payload with plane removed.
        If plane_id not found, returns copy of original.
    """
    new_payload = copy.deepcopy(scene_payload)

    planes = new_payload.get("background_planes", [])
    if not isinstance(planes, list):
        return new_payload

    new_planes = [
        entry for entry in planes
        if not (isinstance(entry, dict) and entry.get("id") == plane_id)
    ]
    new_payload["background_planes"] = new_planes
    return new_payload


def update_background_plane(
    scene_payload: dict[str, Any],
    plane_id: str,
    patch: dict[str, Any],
) -> dict[str, Any]:
    """Update a background plane's fields.

    Sanitizes numeric fields deterministically:
    - parallax: float, clamped [0.0, 2.0]
    - alpha: float, clamped [0.0, 1.0]
    - offset_x, offset_y: float
    - render_layer: int

    If patch contains 'id', enforces uniqueness (rejects collision).

    Args:
        scene_payload: Scene JSON dict
        plane_id: ID of the plane to update
        patch: Dict of field names to new values

    Returns:
        New scene payload with plane updated.
        If plane_id not found or id collision, returns copy of original.
    """
    new_payload = copy.deepcopy(scene_payload)

    planes = new_payload.get("background_planes", [])
    if not isinstance(planes, list):
        return new_payload

    # Find target plane index
    target_idx: int | None = None
    for idx, entry in enumerate(planes):
        if isinstance(entry, dict) and entry.get("id") == plane_id:
            target_idx = idx
            break

    if target_idx is None:
        return new_payload

    # Check for ID change collision
    if "id" in patch:
        new_id = str(patch["id"]).strip()
        if new_id != plane_id:
            existing_ids = _collect_existing_ids(planes)
            existing_ids.discard(plane_id)  # Exclude current plane's ID
            if new_id in existing_ids:
                # Collision - reject change
                return new_payload

    # Apply patch with sanitization
    target_entry = planes[target_idx]
    for key, value in patch.items():
        sanitized = _sanitize_field(key, value)
        if sanitized is not None:
            target_entry[key] = sanitized

    return new_payload


def move_background_plane(
    scene_payload: dict[str, Any],
    plane_id: str,
    direction: str,
) -> dict[str, Any]:
    """Move a background plane up or down in the render order.

    Movement is implemented by adjusting render_layer:
    - "up" decreases render_layer by 1 (renders earlier / behind)
    - "down" increases render_layer by 1 (renders later / in front)

    This keeps ordering deterministic since sort is by (render_layer, id).

    Args:
        scene_payload: Scene JSON dict
        plane_id: ID of the plane to move
        direction: "up" or "down"

    Returns:
        New scene payload with plane's render_layer adjusted.
        If plane_id not found, returns copy of original.
    """
    if direction not in ("up", "down"):
        return copy.deepcopy(scene_payload)

    new_payload = copy.deepcopy(scene_payload)

    planes = new_payload.get("background_planes", [])
    if not isinstance(planes, list):
        return new_payload

    # Find target plane
    target_entry: dict[str, Any] | None = None
    for entry in planes:
        if isinstance(entry, dict) and entry.get("id") == plane_id:
            target_entry = entry
            break

    if target_entry is None:
        return new_payload

    # Get current render_layer
    current_layer = target_entry.get("render_layer", 0)
    if not isinstance(current_layer, int):
        try:
            current_layer = int(current_layer)
        except (TypeError, ValueError):
            current_layer = 0

    # Adjust render_layer
    if direction == "up":
        target_entry["render_layer"] = current_layer - 1
    else:  # direction == "down"
        target_entry["render_layer"] = current_layer + 1

    return new_payload


def get_plane_by_id(
    scene_payload: dict[str, Any],
    plane_id: str,
) -> BackgroundPlane | None:
    """Get a specific background plane by ID.

    Args:
        scene_payload: Scene JSON dict
        plane_id: ID of the plane to find

    Returns:
        BackgroundPlane object if found, None otherwise.
    """
    planes = list_background_planes(scene_payload)
    for plane in planes:
        if plane.id == plane_id:
            return plane
    return None


def compute_tiling_mode(repeat_x: bool, repeat_y: bool) -> str:
    """Compute tiling mode string from repeat flags.

    Args:
        repeat_x: Whether to tile horizontally
        repeat_y: Whether to tile vertically

    Returns:
        One of: "off", "tiled-x", "tiled-y", "tiled-xy"
    """
    if repeat_x and repeat_y:
        return "tiled-xy"
    elif repeat_x:
        return "tiled-x"
    elif repeat_y:
        return "tiled-y"
    return "off"


def parse_tiling_mode(mode: str) -> Tuple[bool, bool]:
    """Parse tiling mode string to repeat flags.

    Args:
        mode: One of "off", "tiled-x", "tiled-y", "tiled-xy"

    Returns:
        Tuple of (repeat_x, repeat_y)
    """
    mode = mode.lower().strip()
    if mode == "tiled-xy":
        return True, True
    elif mode == "tiled-x":
        return True, False
    elif mode == "tiled-y":
        return False, True
    return False, False


# -----------------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------------


def _collect_existing_ids(planes: list[Any]) -> set[str]:
    """Collect all existing plane IDs from list."""
    ids: set[str] = set()
    for entry in planes:
        if isinstance(entry, dict):
            plane_id = entry.get("id")
            if isinstance(plane_id, str) and plane_id.strip():
                ids.add(plane_id.strip())
    return ids


def _generate_unique_id(existing_ids: set[str], prefix: str = "plane") -> str:
    """Generate a unique ID with numeric suffix.

    Tries prefix_001, prefix_002, etc. until finding unused ID.

    Args:
        existing_ids: Set of existing IDs to avoid
        prefix: Base prefix for the ID

    Returns:
        Unique ID string.
    """
    counter = 1
    while True:
        new_id = f"{prefix}_{counter:03d}"
        if new_id not in existing_ids:
            return new_id
        counter += 1
        # Safety limit to prevent infinite loop
        if counter > 99999:
            return f"{prefix}_{counter:05d}"


def _sanitize_field(key: str, value: Any) -> Any | None:
    """Sanitize a field value for storage.

    Returns None if the key is not a known field.

    Args:
        key: Field name
        value: Raw value

    Returns:
        Sanitized value or None if key unknown.
    """
    if key == "id":
        if isinstance(value, str):
            return value.strip() or None
        return None

    if key == "asset_path":
        if isinstance(value, str):
            return value.strip()
        return ""

    if key == "parallax":
        return _safe_float(value, default=0.5, min_val=0.0, max_val=2.0)

    if key == "alpha":
        return _safe_float(value, default=1.0, min_val=0.0, max_val=1.0)

    if key in ("offset_x", "offset_y"):
        return _safe_float(value, default=0.0)

    if key == "render_layer":
        return _safe_int(value, default=0)

    if key in ("repeat_x", "repeat_y"):
        return bool(value)

    if key == "tint":
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            return list(value)
        return None

    return None


def _safe_float(
    value: Any,
    *,
    default: float,
    min_val: float | None = None,
    max_val: float | None = None,
) -> float:
    """Safely convert to float with optional clamping."""
    if value is None:
        return default
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if min_val is not None:
        result = max(min_val, result)
    if max_val is not None:
        result = min(max_val, result)
    return result


def _safe_int(value: Any, *, default: int) -> int:
    """Safely convert to int."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
