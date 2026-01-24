from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from engine.tilemap_edit import TilemapDims, ensure_tiles_array, get_layer_by_id, set_tile


@dataclass(slots=True)
class TilePaintState:
    enabled: bool = False
    layer_id: str = ""
    tile_id: int = 1
    stroke_active: bool = False
    stroke_tool: str = "brush"  # brush|line|rect_outline|rect_fill
    stroke_button: int = 0
    stroke_anchor: tuple[int, int] | None = None
    stroke_last_hit: tuple[int, int] | None = None
    stroke_coords: set[tuple[int, int]] = field(default_factory=set)


def world_to_tile(
    *,
    map_width: int,
    map_height: int,
    tile_width: int,
    tile_height: int,
    world_x: float,
    world_y: float,
) -> tuple[int, int] | None:
    """
    Convert world coordinates (origin at bottom-left) into tile coordinates (x,y) where
    y=0 is the *top* row (matching the row-major override indexing used by Mesh tile layers).
    """
    if map_width <= 0 or map_height <= 0 or tile_width <= 0 or tile_height <= 0:
        return None

    col = int(float(world_x) // float(tile_width))
    row_from_bottom = int(float(world_y) // float(tile_height))
    row = int(map_height - 1 - row_from_bottom)

    if col < 0 or row < 0 or col >= int(map_width) or row >= int(map_height):
        return None
    return (col, row)

def compute_tile_paint_tool(*, shift: bool, ctrl: bool, alt: bool) -> str:
    if bool(ctrl):
        return "rect_fill" if bool(shift) else "rect_outline"
    if bool(alt):
        return "line"
    if bool(shift):
        return "pick"
    return "brush"


def iter_sorted_tile_coords(coords: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    return sorted({(int(x), int(y)) for x, y in coords}, key=lambda p: (p[1], p[0]))


def line_coords_4_connected(*, x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    """
    Deterministic 4-connected line coordinates from (x0,y0) -> (x1,y1), inclusive.

    Uses Bresenham points, then expands diagonal steps by inserting an orthogonal
    intermediate point (x-first) so successive points are always 4-neighbor-adjacent.
    """
    x0 = int(x0)
    y0 = int(y0)
    x1 = int(x1)
    y1 = int(y1)

    points: list[tuple[int, int]] = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        points.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy

    if len(points) <= 1:
        return points

    out: list[tuple[int, int]] = [points[0]]
    for prev, cur in zip(points, points[1:], strict=False):
        px, py = prev
        cx, cy = cur
        if abs(cx - px) == 1 and abs(cy - py) == 1:
            out.append((cx, py))
        out.append((cx, cy))
    return out


def rect_outline_coords(*, x0: int, y0: int, x1: int, y1: int) -> set[tuple[int, int]]:
    x0i, x1i = sorted((int(x0), int(x1)))
    y0i, y1i = sorted((int(y0), int(y1)))
    coords: set[tuple[int, int]] = set()
    for x in range(x0i, x1i + 1):
        coords.add((x, y0i))
        coords.add((x, y1i))
    for y in range(y0i, y1i + 1):
        coords.add((x0i, y))
        coords.add((x1i, y))
    return coords


def rect_fill_coords(*, x0: int, y0: int, x1: int, y1: int) -> set[tuple[int, int]]:
    x0i, x1i = sorted((int(x0), int(x1)))
    y0i, y1i = sorted((int(y0), int(y1)))
    coords: set[tuple[int, int]] = set()
    for y in range(y0i, y1i + 1):
        for x in range(x0i, x1i + 1):
            coords.add((x, y))
    return coords


def peek_tile_value(
    scene_payload: dict[str, Any],
    *,
    layer_id: str,
    tx: int,
    ty: int,
    map_width: int,
    map_height: int,
) -> int | None:
    tilemap = scene_payload.get("tilemap")
    if not isinstance(tilemap, dict):
        return None
    tile_layers = tilemap.get("tile_layers")
    if not isinstance(tile_layers, list):
        return None
    layer = next((e for e in tile_layers if isinstance(e, dict) and e.get("id") == str(layer_id)), None)
    if not isinstance(layer, dict):
        return None
    tiles = layer.get("tiles")
    if not isinstance(tiles, list):
        return None
    if len(tiles) != int(map_width) * int(map_height):
        return None
    idx = int(ty) * int(map_width) + int(tx)
    if idx < 0 or idx >= len(tiles):
        return None
    v = tiles[idx]
    return int(v) if isinstance(v, int) else None


def iter_sorted_tile_layer_ids(tile_layers: Iterable[object]) -> list[str]:
    ids: list[str] = []
    for entry in tile_layers:
        if not isinstance(entry, dict):
            continue
        layer_id = entry.get("id")
        if isinstance(layer_id, str) and layer_id.strip():
            ids.append(layer_id.strip())
    return sorted(set(ids))


def cycle_layer_id(*, tile_layers: Iterable[object], current: str, direction: int) -> str:
    ids = iter_sorted_tile_layer_ids(tile_layers)
    if not ids:
        return ""
    cur = str(current or "").strip()
    if cur not in ids:
        return ids[0]
    idx = ids.index(cur)
    step = 1 if int(direction) >= 0 else -1
    return ids[(idx + step) % len(ids)]


def apply_paint(
    scene_payload: dict[str, Any],
    *,
    layer_id: str,
    tx: int,
    ty: int,
    tile_id: int,
    map_width: int,
    map_height: int,
) -> bool:
    tilemap = scene_payload.get("tilemap")
    if not isinstance(tilemap, dict):
        return False
    tile_layers = tilemap.get("tile_layers")
    if not isinstance(tile_layers, list):
        return False

    dims = TilemapDims(width=int(map_width), height=int(map_height))
    layer = get_layer_by_id(tile_layers, str(layer_id))

    tiles = ensure_tiles_array(layer, dims=dims)
    return set_tile(tiles, dims=dims, x=int(tx), y=int(ty), tile=int(tile_id))


def apply_erase(
    scene_payload: dict[str, Any],
    *,
    layer_id: str,
    tx: int,
    ty: int,
    map_width: int,
    map_height: int,
) -> bool:
    return apply_paint(
        scene_payload,
        layer_id=layer_id,
        tx=tx,
        ty=ty,
        tile_id=0,
        map_width=map_width,
        map_height=map_height,
    )
