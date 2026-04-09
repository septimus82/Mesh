from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol
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
    """
    factor = float(parallax) * float(zoom)
    return (-float(camera_x) * factor, -float(camera_y) * factor)


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

        layers.append(
            BackgroundLayer(
                id=layer_id,
                path=str(path).strip(),
                z=int(z),
                parallax=parallax,
                repeat_x=repeat_x,
                repeat_y=repeat_y,
            )
        )

    return sort_background_layers(layers)


def draw_background_layers(
    layers: list[BackgroundLayer],
    *,
    camera_x: float,
    camera_y: float,
    viewport_w: float,
    viewport_h: float,
    zoom: float = 1.0,
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

    center_x = float(viewport_w) / 2.0
    center_y = float(viewport_h) / 2.0

    for layer in sort_background_layers(list(layers)):
        texture = fetch(layer.path)
        if texture is None:
            continue

        offset_x, offset_y = compute_background_offset_px(
            camera_x=float(camera_x),
            camera_y=float(camera_y),
            parallax=float(layer.parallax),
            zoom=float(zoom),
        )
        base_x = center_x + offset_x
        base_y = center_y + offset_y

        tile_w = max(1.0, float(texture.width))
        tile_h = max(1.0, float(texture.height))

        if not layer.repeat_x and not layer.repeat_y:
            draw(base_x, base_y, float(texture.width), float(texture.height), texture)
            continue

        # Determine tiling ranges (inclusive).
        x_range = (0, 0)
        y_range = (0, 0)
        if layer.repeat_x:
            left_needed = -tile_w / 2.0
            right_needed = float(viewport_w) + tile_w / 2.0
            n_min = int((left_needed - base_x) // tile_w) - 1
            n_max = int((right_needed - base_x) // tile_w) + 1
            x_range = (n_min, n_max)
        if layer.repeat_y:
            bottom_needed = -tile_h / 2.0
            top_needed = float(viewport_h) + tile_h / 2.0
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
    optional_arcade.arcade.draw_texture_rectangle(
        float(center_x),
        float(center_y),
        float(width),
        float(height),
        texture,
    )
