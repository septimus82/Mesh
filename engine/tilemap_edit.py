from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TilemapDims:
    width: int
    height: int

    def tile_count(self) -> int:
        return int(self.width) * int(self.height)


def get_layer_by_id(tile_layers: list[object], layer_id: str) -> dict:
    wanted = str(layer_id or "").strip()
    if not wanted:
        raise ValueError("missing layer_id")
    for entry in tile_layers:
        if isinstance(entry, dict) and entry.get("id") == wanted:
            return entry
    raise KeyError(wanted)


def ensure_tiles_array(layer: dict, *, dims: TilemapDims) -> list[int]:
    if dims.width <= 0 or dims.height <= 0:
        raise ValueError("invalid tilemap dimensions")

    tiles = layer.get("tiles")
    if tiles is None:
        new_tiles = [0] * dims.tile_count()
        layer["tiles"] = new_tiles
        return new_tiles
    if not isinstance(tiles, list):
        raise TypeError("layer.tiles must be a list")
    bad_index = next((i for i, v in enumerate(tiles) if not isinstance(v, int)), None)
    if bad_index is not None:
        raise TypeError(f"layer.tiles[{bad_index}] must be an int")
    if len(tiles) != dims.tile_count():
        raise ValueError(f"layer.tiles expected {dims.tile_count()} entries, got {len(tiles)}")
    return tiles


def _index(*, width: int, x: int, y: int) -> int:
    return int(y) * int(width) + int(x)


def set_tile(tiles: list[int], *, dims: TilemapDims, x: int, y: int, tile: int) -> bool:
    if x < 0 or y < 0 or x >= dims.width or y >= dims.height:
        raise IndexError(f"tile coord out of bounds: ({x}, {y}) in {dims.width}x{dims.height}")
    idx = _index(width=dims.width, x=x, y=y)
    desired = int(tile)
    if tiles[idx] == desired:
        return False
    tiles[idx] = desired
    return True


def fill_rect(
    tiles: list[int],
    *,
    dims: TilemapDims,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    tile: int,
) -> bool:
    """Fill inclusive tile rect [x0..x1] x [y0..y1] with `tile`."""
    if x0 > x1 or y0 > y1:
        raise ValueError("rect must satisfy x0<=x1 and y0<=y1")
    if x0 < 0 or y0 < 0 or x1 >= dims.width or y1 >= dims.height:
        raise IndexError(f"rect out of bounds: ({x0},{y0})..({x1},{y1}) in {dims.width}x{dims.height}")

    changed = False
    for y in range(int(y0), int(y1) + 1):
        row_start = _index(width=dims.width, x=int(x0), y=y)
        row_end = _index(width=dims.width, x=int(x1), y=y)
        desired = int(tile)
        for idx in range(row_start, row_end + 1):
            if tiles[idx] != desired:
                tiles[idx] = desired
                changed = True
    return changed


def clear_rect(
    tiles: list[int],
    *,
    dims: TilemapDims,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
) -> bool:
    """Clear inclusive tile rect [x0..x1] x [y0..y1] (set to 0)."""
    return fill_rect(tiles, dims=dims, x0=x0, y0=y0, x1=x1, y1=y1, tile=0)

