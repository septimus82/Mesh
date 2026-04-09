from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, cast

TileCoord = tuple[int, int]


@dataclass(frozen=True, slots=True)
class NavGrid:
    width: int
    height: int
    tile_w: int
    tile_h: int
    blocked: frozenset[int]

    def in_bounds(self, pos: TileCoord) -> bool:
        x, y = pos
        return 0 <= x < self.width and 0 <= y < self.height

    def to_index(self, pos: TileCoord) -> int:
        x, y = pos
        return y * self.width + x

    def is_walkable(self, pos: TileCoord) -> bool:
        if not self.in_bounds(pos):
            return False
        return self.to_index(pos) not in self.blocked

    def tile_center_world(self, pos: TileCoord) -> tuple[float, float]:
        x, y = pos
        return ((x + 0.5) * float(self.tile_w), (y + 0.5) * float(self.tile_h))

    def world_to_tile(self, world_x: float, world_y: float) -> TileCoord:
        x = int(float(world_x) // float(self.tile_w)) if self.tile_w > 0 else 0
        y = int(float(world_y) // float(self.tile_h)) if self.tile_h > 0 else 0
        return (x, y)


def _parse_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:  # noqa: BLE001  # REASON: malformed integer-like nav-grid values should fall back to zero during payload parsing
        return 0


def build_nav_grid_from_scene_payload(scene_payload: dict[str, Any]) -> NavGrid | None:
    """
    Build a NavGrid from an authored scene payload containing in-scene tile layer overrides.

    This does not load external Tiled maps; it only consumes scene["tilemap"]["tile_layers"].
    """
    tilemap = scene_payload.get("tilemap")
    if not isinstance(tilemap, dict):
        return None

    width = _parse_int(tilemap.get("width"))
    height = _parse_int(tilemap.get("height"))
    tile_w = _parse_int(tilemap.get("tilewidth"))
    tile_h = _parse_int(tilemap.get("tileheight"))
    if width <= 0 or height <= 0 or tile_w <= 0 or tile_h <= 0:
        return None

    collision_layer_id = tilemap.get("collision_layer_id")
    if not isinstance(collision_layer_id, str) or not collision_layer_id.strip():
        return NavGrid(width=width, height=height, tile_w=tile_w, tile_h=tile_h, blocked=frozenset())
    collision_layer_id = collision_layer_id.strip()

    layers = tilemap.get("tile_layers")
    if not isinstance(layers, list):
        return None

    blocked: set[int] = set()
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        layer_id = layer.get("id")
        if not isinstance(layer_id, str) or layer_id.strip() != collision_layer_id:
            continue
        tiles = layer.get("tiles")
        if not isinstance(tiles, list):
            continue
        expected = width * height
        if len(tiles) != expected:
            return None
        for idx, tile in enumerate(tiles):
            try:
                if int(tile) != 0:
                    blocked.add(idx)
            except Exception:  # noqa: BLE001  # REASON: malformed authored collision tile values should invalidate that nav-grid payload build
                return None
        break

    return NavGrid(width=width, height=height, tile_w=tile_w, tile_h=tile_h, blocked=frozenset(blocked))


def build_nav_grid_from_tilemap_instance(tilemap_instance: Any) -> NavGrid | None:
    """
    Build a NavGrid from a runtime TilemapInstance-like object.

    Uses collision sprites to mark blocked tiles, which matches runtime collision.
    """
    if tilemap_instance is None:
        return None

    map_size = getattr(tilemap_instance, "map_size", None)
    tile_size = getattr(tilemap_instance, "tile_size", None)
    if not isinstance(map_size, tuple) or len(map_size) != 2:
        return None
    if not isinstance(tile_size, tuple) or len(tile_size) != 2:
        return None
    width, height = int(map_size[0]), int(map_size[1])
    tile_w, tile_h = int(tile_size[0]), int(tile_size[1])
    if width <= 0 or height <= 0 or tile_w <= 0 or tile_h <= 0:
        return None

    collision_sprites = getattr(tilemap_instance, "collision_sprites", None)
    blocked: set[int] = set()

    def _iter_sprites(value: Any) -> Iterable[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if hasattr(value, "__iter__"):
            return cast(Iterable[Any], value)
        return []

    for sprite in _iter_sprites(collision_sprites):
        try:
            tx = int(float(getattr(sprite, "center_x")) // float(tile_w))
            ty = int(float(getattr(sprite, "center_y")) // float(tile_h))
        except Exception:  # noqa: BLE001  # REASON: malformed collision sprite positions should skip only that sprite when building the runtime nav grid
            continue
        if 0 <= tx < width and 0 <= ty < height:
            blocked.add(ty * width + tx)

    return NavGrid(width=width, height=height, tile_w=tile_w, tile_h=tile_h, blocked=frozenset(blocked))
