"""Pure model for parallax background planes.

Provides HD-2D style parallax backgrounds that move relative to camera.

Parallax factor:
- 0.0 = fixed to screen (doesn't move with camera)
- 1.0 = moves with world (same as entities)
- 0.5 = moves at half speed (appears further back)
- values > 1.0 = moves faster than camera (foreground parallax)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Tuple


@dataclass(frozen=True, slots=True)
class BackgroundPlane:
    """A parallax background plane for HD-2D rendering.

    Attributes:
        asset_path: Path to the background image asset
        parallax: Movement factor relative to camera (0.0 = fixed, 1.0 = world)
        render_layer: Draw order within background planes (lower = further back)
        alpha: Opacity from 0.0 (transparent) to 1.0 (opaque)
        tint: Optional RGBA tint color tuple
        offset_x: Horizontal offset in pixels
        offset_y: Vertical offset in pixels
        repeat_x: Whether to tile horizontally
        repeat_y: Whether to tile vertically
        id: Unique identifier for this plane
    """

    asset_path: str
    parallax: float = 0.5
    render_layer: int = 0
    alpha: float = 1.0
    tint: Tuple[int, int, int, int] | None = None
    offset_x: float = 0.0
    offset_y: float = 0.0
    repeat_x: bool = False
    repeat_y: bool = False
    id: str = ""


def compute_parallax_offset(
    camera_x: float,
    camera_y: float,
    parallax: float,
) -> Tuple[float, float]:
    """Compute screen-space offset for a parallax layer.

    The offset represents how much the layer should shift from its base position
    based on the camera position.

    Args:
        camera_x: Camera center x in world coordinates
        camera_y: Camera center y in world coordinates
        parallax: Parallax factor (0.0 = fixed, 1.0 = moves with world)

    Returns:
        Tuple (dx, dy) offset in screen-space pixels.
        Apply this offset to the layer's base screen position.
    """
    factor = float(parallax)
    # Negative because when camera moves right, background should appear to move left
    dx = -float(camera_x) * factor
    dy = -float(camera_y) * factor
    return (dx, dy)


def compute_parallax_offset_with_zoom(
    camera_x: float,
    camera_y: float,
    parallax: float,
    zoom: float = 1.0,
) -> Tuple[float, float]:
    """Compute parallax offset accounting for camera zoom.

    Args:
        camera_x: Camera center x in world coordinates
        camera_y: Camera center y in world coordinates
        parallax: Parallax factor (0.0 = fixed, 1.0 = moves with world)
        zoom: Camera zoom level (1.0 = normal, 2.0 = 2x zoom)

    Returns:
        Tuple (dx, dy) offset in screen-space pixels.
    """
    factor = float(parallax) * float(zoom)
    dx = -float(camera_x) * factor
    dy = -float(camera_y) * factor
    return (dx, dy)


def sort_background_planes(planes: Iterable[BackgroundPlane]) -> list[BackgroundPlane]:
    """Sort background planes by render order.

    Lower render_layer draws first (further back).
    Ties broken by id for determinism.

    Args:
        planes: Iterable of BackgroundPlane objects

    Returns:
        List sorted by (render_layer, id).
    """
    return sorted(planes, key=lambda p: (p.render_layer, p.id))


def parse_background_planes(scene_payload: dict[str, Any]) -> list[BackgroundPlane]:
    """Parse background_planes from scene payload.

    Expects scene_payload["background_planes"] to be a list of dicts with:
    - asset_path (required): str
    - parallax (optional): float, default 0.5
    - render_layer (optional): int, default 0
    - alpha (optional): float, default 1.0
    - tint (optional): [r, g, b, a] list
    - offset_x, offset_y (optional): float, default 0.0
    - repeat_x, repeat_y (optional): bool, default False
    - id (optional): str

    Args:
        scene_payload: Scene JSON dict

    Returns:
        List of BackgroundPlane objects, sorted by render order.
    """
    raw = scene_payload.get("background_planes")
    if raw is None:
        return []
    if not isinstance(raw, list):
        return []

    planes: list[BackgroundPlane] = []
    seen_ids: set[str] = set()

    for idx, entry in enumerate(raw):
        if not isinstance(entry, dict):
            continue

        # Required: asset_path
        asset_path = entry.get("asset_path")
        if not isinstance(asset_path, str) or not asset_path.strip():
            continue
        asset_path = asset_path.strip()

        # Optional fields with defaults
        parallax = _safe_float(entry.get("parallax"), default=0.5, min_val=0.0, max_val=2.0)
        render_layer = _safe_int(entry.get("render_layer"), default=0)
        alpha = _safe_float(entry.get("alpha"), default=1.0, min_val=0.0, max_val=1.0)
        offset_x = _safe_float(entry.get("offset_x"), default=0.0)
        offset_y = _safe_float(entry.get("offset_y"), default=0.0)
        repeat_x = bool(entry.get("repeat_x", False))
        repeat_y = bool(entry.get("repeat_y", False))

        # Tint color
        tint: Tuple[int, int, int, int] | None = None
        raw_tint = entry.get("tint")
        if isinstance(raw_tint, (list, tuple)) and len(raw_tint) >= 3:
            try:
                r = max(0, min(255, int(raw_tint[0])))
                g = max(0, min(255, int(raw_tint[1])))
                b = max(0, min(255, int(raw_tint[2])))
                a = max(0, min(255, int(raw_tint[3]))) if len(raw_tint) >= 4 else 255
                tint = (r, g, b, a)
            except (TypeError, ValueError):
                pass

        # ID with auto-generation for duplicates
        plane_id = entry.get("id")
        if not isinstance(plane_id, str) or not plane_id.strip():
            plane_id = f"plane_{idx}"
        else:
            plane_id = plane_id.strip()

        # Ensure unique ID
        if plane_id in seen_ids:
            base_id = plane_id
            counter = 1
            while plane_id in seen_ids:
                plane_id = f"{base_id}_{counter}"
                counter += 1
        seen_ids.add(plane_id)

        planes.append(
            BackgroundPlane(
                asset_path=asset_path,
                parallax=parallax,
                render_layer=render_layer,
                alpha=alpha,
                tint=tint,
                offset_x=offset_x,
                offset_y=offset_y,
                repeat_x=repeat_x,
                repeat_y=repeat_y,
                id=plane_id,
            )
        )

    return sort_background_planes(planes)


def background_planes_to_payloads(planes: Iterable[BackgroundPlane]) -> list[dict[str, Any]]:
    """Convert BackgroundPlane objects to JSON-serializable dicts.

    Args:
        planes: Iterable of BackgroundPlane objects

    Returns:
        List of dicts suitable for JSON serialization.
    """
    payloads: list[dict[str, Any]] = []
    for plane in planes:
        payload: dict[str, Any] = {
            "id": plane.id,
            "asset_path": plane.asset_path,
            "parallax": plane.parallax,
            "render_layer": plane.render_layer,
        }
        if plane.alpha != 1.0:
            payload["alpha"] = plane.alpha
        if plane.tint is not None:
            payload["tint"] = list(plane.tint)
        if plane.offset_x != 0.0:
            payload["offset_x"] = plane.offset_x
        if plane.offset_y != 0.0:
            payload["offset_y"] = plane.offset_y
        if plane.repeat_x:
            payload["repeat_x"] = True
        if plane.repeat_y:
            payload["repeat_y"] = True
        payloads.append(payload)
    return payloads


# -----------------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------------


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
