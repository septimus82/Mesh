from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal, Protocol

import engine.optional_arcade as optional_arcade

from .logging_tools import get_logger
from .paths import resolve_path

logger = get_logger(__name__)


class TextureLike(Protocol):
    width: int
    height: int


@dataclass(slots=True)
class BackgroundLayer:
    id: str
    path: str
    z: int
    parallax: float = 1.0
    repeat_x: bool = False
    repeat_y: bool = False
    anchor_x: float = 0.0
    anchor_y: float = 0.0
    anchor: str | None = None


class BackgroundTextureCache:
    def __init__(self) -> None:
        self._cache: dict[str, optional_arcade.arcade.Texture] = {}

    def get(self, path: str) -> optional_arcade.arcade.Texture | None:
        raw = str(path or "").strip()
        if not raw:
            return None
        resolved = resolve_path(raw)
        key = str(resolved)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        if not resolved.exists():
            logger.warning("Missing background texture '%s'", raw)
            return None
        try:
            tex = optional_arcade.arcade.load_texture(str(resolved))
        except Exception as exc:  # noqa: BLE001  # REASON: optional texture load failures should degrade to a warning instead of aborting scene setup
            logger.warning("Failed to load texture '%s': %s", raw, exc)
            return None
        self._cache[key] = tex
        return tex


_DEFAULT_CACHE = BackgroundTextureCache()


def sort_background_layers(layers: list[BackgroundLayer]) -> list[BackgroundLayer]:
    return sorted(layers, key=lambda layer: (int(layer.z), str(layer.id)))


def compute_background_offset_px(
    *,
    camera_x: float,
    camera_y: float,
    parallax: float,
    zoom: float = 1.0,
) -> tuple[float, float]:
    """Compute a screen-space offset for a layer given camera center in world space.

    Parallax model: the layer shifts by `-camera * parallax` (scaled by zoom).
    - `parallax=1.0` tracks the world camera normally.
    - `parallax=0.0` locks to the screen (no movement).

    Used by the legacy screen-space draw path (``coordinate_space="screen"``).
    """
    factor = float(parallax) * float(zoom)
    return (-float(camera_x) * factor, -float(camera_y) * factor)


def compute_background_world_center(
    *,
    camera_x: float,
    camera_y: float,
    parallax: float,
    anchor_x: float = 0.0,
    anchor_y: float = 0.0,
) -> tuple[float, float]:
    """Return the world-space center for a background layer texture.

    ``parallax=1.0`` anchors the layer to ``anchor`` (default world origin).
    ``parallax=0.0`` locks the layer to the camera center (screen-fixed backdrop).
    Intermediate values interpolate between anchor and camera for parallax depth.
    """
    t = float(parallax)
    cx = float(camera_x)
    cy = float(camera_y)
    return (
        float(anchor_x) * t + cx * (1.0 - t),
        float(anchor_y) * t + cy * (1.0 - t),
    )


def compute_background_screen_center(
    *,
    camera_x: float,
    camera_y: float,
    parallax: float,
    viewport_w: float,
    viewport_h: float,
    zoom: float = 1.0,
    anchor_x: float = 0.0,
    anchor_y: float = 0.0,
) -> tuple[float, float]:
    """Project a parallax layer's world center to GUI/screen pixel coordinates.

    Use with ``gui_camera`` (including inside Arcade LightLayer capture) so the
    draw lands in the active diffuse framebuffer. ``parallax=0`` stays centred
    on screen when the camera pans; ``parallax=1`` anchors to ``anchor`` in world
    space and scrolls correctly as the camera moves.
    """
    wx, wy = compute_background_world_center(
        camera_x=camera_x,
        camera_y=camera_y,
        parallax=parallax,
        anchor_x=anchor_x,
        anchor_y=anchor_y,
    )
    safe_zoom = float(zoom) if float(zoom) > 0.0 else 1.0
    sx = (wx - float(camera_x)) * safe_zoom + float(viewport_w) / 2.0
    sy = (wy - float(camera_y)) * safe_zoom + float(viewport_h) / 2.0
    return (sx, sy)


def resolve_background_layer_anchor(
    layer: BackgroundLayer,
    *,
    texture_width: float,
    texture_height: float,
) -> tuple[float, float]:
    """Resolve the world-space anchor used by ``compute_background_world_center``."""
    anchor_mode = str(layer.anchor or "").strip()
    if anchor_mode == "world_rect":
        return (float(texture_width) / 2.0, float(texture_height) / 2.0)
    return (float(layer.anchor_x), float(layer.anchor_y))


def compute_texture_world_bounds(
    *,
    center_x: float,
    center_y: float,
    width: float,
    height: float,
) -> tuple[float, float, float, float]:
    """Return ``(left, bottom, right, top)`` for a center-anchored texture quad."""
    half_w = float(width) / 2.0
    half_h = float(height) / 2.0
    return (
        float(center_x) - half_w,
        float(center_y) - half_h,
        float(center_x) + half_w,
        float(center_y) + half_h,
    )


def clamp_camera_to_world_bounds(
    target_x: float,
    target_y: float,
    *,
    world_width: float,
    world_height: float,
    viewport_width: float,
    viewport_height: float,
    padding: float = 0.0,
) -> tuple[float, float]:
    """Clamp a camera center so the viewport stays inside ``[0,W]x[0,H]``."""
    half_w = float(viewport_width) / 2.0
    half_h = float(viewport_height) / 2.0
    padded_half_w = half_w + float(padding)
    padded_half_h = half_h + float(padding)

    min_x = padded_half_w
    max_x = max(padded_half_w, float(world_width) - padded_half_w)
    min_y = padded_half_h
    max_y = max(padded_half_h, float(world_height) - padded_half_h)

    clamped_x = min(max(float(target_x), min_x), max_x)
    clamped_y = min(max(float(target_y), min_y), max_y)
    return (clamped_x, clamped_y)


def compute_viewport_world_bounds(
    *,
    camera_x: float,
    camera_y: float,
    viewport_width: float,
    viewport_height: float,
) -> tuple[float, float, float, float]:
    """Return ``(left, bottom, right, top)`` for the visible world rectangle."""
    half_w = float(viewport_width) / 2.0
    half_h = float(viewport_height) / 2.0
    cx = float(camera_x)
    cy = float(camera_y)
    return (cx - half_w, cy - half_h, cx + half_w, cy + half_h)


def viewport_is_inside_texture(
    *,
    camera_x: float,
    camera_y: float,
    viewport_width: float,
    viewport_height: float,
    texture_width: float,
    texture_height: float,
    layer: BackgroundLayer,
) -> bool:
    """Return True when the viewport lies fully inside a non-repeating layer texture."""
    anchor_x, anchor_y = resolve_background_layer_anchor(
        layer,
        texture_width=float(texture_width),
        texture_height=float(texture_height),
    )
    center_x, center_y = compute_background_world_center(
        camera_x=float(camera_x),
        camera_y=float(camera_y),
        parallax=float(layer.parallax),
        anchor_x=anchor_x,
        anchor_y=anchor_y,
    )
    tex_left, tex_bottom, tex_right, tex_top = compute_texture_world_bounds(
        center_x=center_x,
        center_y=center_y,
        width=float(texture_width),
        height=float(texture_height),
    )
    view_left, view_bottom, view_right, view_top = compute_viewport_world_bounds(
        camera_x=float(camera_x),
        camera_y=float(camera_y),
        viewport_width=float(viewport_width),
        viewport_height=float(viewport_height),
    )
    return (
        view_left >= tex_left
        and view_bottom >= tex_bottom
        and view_right <= tex_right
        and view_top <= tex_top
    )


def parse_background_layers(scene_payload: dict[str, Any]) -> list[BackgroundLayer]:
    raw = scene_payload.get("background_layers")
    if raw is None:
        return []
    if not isinstance(raw, list):
        logger.warning("scene.background_layers must be an array; ignoring")
        return []

    layers: list[BackgroundLayer] = []
    seen: set[str] = set()
    for idx, entry in enumerate(raw):
        if not isinstance(entry, dict):
            logger.warning("background_layers[%d] must be an object; skipping", idx)
            continue
        layer_id = entry.get("id")
        if not isinstance(layer_id, str) or not layer_id.strip():
            logger.warning("background_layers[%d].id must be a non-empty string; skipping", idx)
            continue
        layer_id = layer_id.strip()
        if layer_id in seen:
            logger.warning("Duplicate background layer id '%s'; skipping", layer_id)
            continue
        seen.add(layer_id)

        path = entry.get("path")
        if not isinstance(path, str) or not path.strip():
            logger.warning("background_layers[%d].path must be a non-empty string; skipping", idx)
            continue

        z = entry.get("z")
        if not isinstance(z, int):
            logger.warning("background_layers[%d].z must be an int; skipping", idx)
            continue

        parallax_value = entry.get("parallax", 1.0)
        try:
            parallax = float(parallax_value)
        except (TypeError, ValueError):
            logger.warning(
                "background_layers[%d].parallax must be a number; defaulting to 1.0", idx
            )
            parallax = 1.0
        parallax = max(0.0, min(2.0, parallax))

        repeat_x = bool(entry.get("repeat_x", False))
        repeat_y = bool(entry.get("repeat_y", False))
        # Backward compatibility for earlier `repeat` flag (treated as repeat_x).
        if "repeat" in entry and "repeat_x" not in entry:
            repeat_x = bool(entry.get("repeat", False))

        anchor_x = 0.0
        anchor_y = 0.0
        if "anchor_x" in entry:
            try:
                anchor_x = float(entry.get("anchor_x"))
            except (TypeError, ValueError):
                logger.warning(
                    "background_layers[%d].anchor_x must be a number; defaulting to 0.0", idx
                )
                anchor_x = 0.0
        if "anchor_y" in entry:
            try:
                anchor_y = float(entry.get("anchor_y"))
            except (TypeError, ValueError):
                logger.warning(
                    "background_layers[%d].anchor_y must be a number; defaulting to 0.0", idx
                )
                anchor_y = 0.0

        anchor_mode: str | None = None
        anchor_raw = entry.get("anchor")
        if isinstance(anchor_raw, str) and anchor_raw.strip():
            anchor_mode = anchor_raw.strip()
            if anchor_mode not in {"world_rect"}:
                logger.warning(
                    "background_layers[%d].anchor '%s' is unknown; ignoring",
                    idx,
                    anchor_mode,
                )
                anchor_mode = None

        layers.append(
            BackgroundLayer(
                id=layer_id,
                path=str(path).strip(),
                z=int(z),
                parallax=parallax,
                repeat_x=repeat_x,
                repeat_y=repeat_y,
                anchor_x=anchor_x,
                anchor_y=anchor_y,
                anchor=anchor_mode,
            )
        )

    return sort_background_layers(layers)


def parse_foreground_layers(scene_payload: dict[str, Any]) -> list[BackgroundLayer]:
    """Parse scene.foreground_layers (same shape/validation as background_layers).

    Foreground layers render AFTER entities (in front of the player) — e.g. the
    RPG-Maker 'ParallaxUpper' canopy the player can walk behind.
    """
    raw = scene_payload.get("foreground_layers")
    if raw is None:
        return []
    return parse_background_layers({"background_layers": raw})


def draw_background_layers(
    layers: list[BackgroundLayer],
    *,
    camera_x: float,
    camera_y: float,
    viewport_w: float,
    viewport_h: float,
    zoom: float = 1.0,
    coordinate_space: Literal["screen", "world", "projected"] = "projected",
    texture_cache: BackgroundTextureCache | None = None,
    draw_texture: Callable[[float, float, float, float, TextureLike], None] | None = None,
    get_texture: Callable[[str], TextureLike | None] | None = None,
) -> None:
    if not layers:
        return

    draw = draw_texture or _draw_texture_rectangle
    if get_texture is None:
        cache = texture_cache or _DEFAULT_CACHE
        fetch: Callable[[str], TextureLike | None] = cache.get
    else:
        fetch = get_texture

    if coordinate_space == "world":
        safe_zoom = float(zoom) if float(zoom) > 0.0 else 1.0
        span_w = float(viewport_w) / safe_zoom
        span_h = float(viewport_h) / safe_zoom
        view_left = float(camera_x) - span_w / 2.0
        view_right = float(camera_x) + span_w / 2.0
        view_bottom = float(camera_y) - span_h / 2.0
        view_top = float(camera_y) + span_h / 2.0
    else:
        span_w = float(viewport_w)
        span_h = float(viewport_h)
        view_left = 0.0
        view_right = span_w
        view_bottom = 0.0
        view_top = span_h

    center_x = float(viewport_w) / 2.0
    center_y = float(viewport_h) / 2.0

    for layer in sort_background_layers(list(layers)):
        texture = fetch(layer.path)
        if texture is None:
            continue

        tile_w = max(1.0, float(texture.width))
        tile_h = max(1.0, float(texture.height))
        anchor_x, anchor_y = resolve_background_layer_anchor(
            layer,
            texture_width=tile_w,
            texture_height=tile_h,
        )

        if coordinate_space == "world":
            base_x, base_y = compute_background_world_center(
                camera_x=float(camera_x),
                camera_y=float(camera_y),
                parallax=float(layer.parallax),
                anchor_x=anchor_x,
                anchor_y=anchor_y,
            )
        elif coordinate_space == "projected":
            base_x, base_y = compute_background_screen_center(
                camera_x=float(camera_x),
                camera_y=float(camera_y),
                parallax=float(layer.parallax),
                viewport_w=float(viewport_w),
                viewport_h=float(viewport_h),
                zoom=float(zoom),
                anchor_x=anchor_x,
                anchor_y=anchor_y,
            )
        else:
            offset_x, offset_y = compute_background_offset_px(
                camera_x=float(camera_x),
                camera_y=float(camera_y),
                parallax=float(layer.parallax),
                zoom=float(zoom),
            )
            base_x = center_x + offset_x
            base_y = center_y + offset_y

        if not layer.repeat_x and not layer.repeat_y:
            draw(base_x, base_y, float(texture.width), float(texture.height), texture)
            continue

        # Determine tiling ranges (inclusive) over the visible span.
        x_range = (0, 0)
        y_range = (0, 0)
        if layer.repeat_x:
            left_needed = view_left - tile_w / 2.0
            right_needed = view_right + tile_w / 2.0
            n_min = int((left_needed - base_x) // tile_w) - 1
            n_max = int((right_needed - base_x) // tile_w) + 1
            x_range = (n_min, n_max)
        if layer.repeat_y:
            bottom_needed = view_bottom - tile_h / 2.0
            top_needed = view_top + tile_h / 2.0
            m_min = int((bottom_needed - base_y) // tile_h) - 1
            m_max = int((top_needed - base_y) // tile_h) + 1
            y_range = (m_min, m_max)

        for xi in range(x_range[0], x_range[1] + 1):
            for yi in range(y_range[0], y_range[1] + 1):
                dx = float(xi) * tile_w if layer.repeat_x else 0.0
                dy = float(yi) * tile_h if layer.repeat_y else 0.0
                draw(base_x + dx, base_y + dy, float(texture.width), float(texture.height), texture)


def _draw_texture_rectangle(
    center_x: float,
    center_y: float,
    width: float,
    height: float,
    texture: TextureLike,
) -> None:
    optional_arcade.draw_texture_rect_compat(
        float(center_x),
        float(center_y),
        float(width),
        float(height),
        texture,
    )
