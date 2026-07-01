"""Convert RPG Maker MZ map passability into Mesh collision tile grids."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Sequence


def tile_id_at(data: Sequence[int], *, width: int, height: int, x: int, y: int, layer: int) -> int:
    """Return the MZ map tile id at (x, y) on layer z (0-5)."""
    if not (0 <= x < width and 0 <= y < height and 0 <= layer < 6):
        return 0
    return int(data[layer * width * height + y * width + x] or 0)


def is_tile_fully_impassable(flags: Sequence[int], tile_id: int) -> bool:
    if tile_id <= 0 or tile_id >= len(flags):
        return False
    return (int(flags[tile_id]) & 0x0F) == 0x0F


def is_rmmz_cell_blocked(
    data: Sequence[int],
    flags: Sequence[int],
    *,
    width: int,
    height: int,
    x: int,
    y: int,
    block_regions: Iterable[int] = (1,),
) -> bool:
    """Mirror Map002 collision: region blocks + impassable tiles on any layer."""
    region = tile_id_at(data, width=width, height=height, x=x, y=y, layer=5)
    if region in set(block_regions):
        return True
    for layer in range(6):
        tile_id = tile_id_at(data, width=width, height=height, x=x, y=y, layer=layer)
        if is_tile_fully_impassable(flags, tile_id):
            return True
    return False


def blocked_mask_from_rmmz_map(
    map_payload: dict[str, Any],
    tileset_payload: dict[str, Any],
    *,
    block_regions: Iterable[int] = (1,),
) -> tuple[int, int, list[int]]:
    """Build a row-major blocked mask (1=solid, 0=open) from an MZ map + tileset."""
    width = int(map_payload.get("width", 0))
    height = int(map_payload.get("height", 0))
    data = map_payload.get("data")
    flags = tileset_payload.get("flags")
    if width <= 0 or height <= 0 or not isinstance(data, list) or not isinstance(flags, list):
        raise ValueError("invalid RMMZ map or tileset payload")

    tiles: list[int] = []
    for y in range(height):
        for x in range(width):
            blocked = is_rmmz_cell_blocked(
                data,
                flags,
                width=width,
                height=height,
                x=x,
                y=y,
                block_regions=block_regions,
            )
            tiles.append(1 if blocked else 0)
    return width, height, tiles


def load_rmmz_map(map_path: str | Path) -> dict[str, Any]:
    path = Path(map_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"RMMZ map must be a JSON object: {path}")
    return payload


def load_rmmz_tileset(tilesets_path: str | Path, tileset_id: int) -> dict[str, Any]:
    path = Path(tilesets_path)
    tilesets = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(tilesets, list):
        raise ValueError(f"Tilesets file must be a JSON array: {path}")
    if tileset_id < 0 or tileset_id >= len(tilesets) or tilesets[tileset_id] is None:
        raise ValueError(f"tileset id {tileset_id} not found in {path}")
    entry = tilesets[tileset_id]
    if not isinstance(entry, dict):
        raise ValueError(f"tileset id {tileset_id} is not an object")
    return entry


def mesh_tilemap_from_rmmz_map(
    map_path: str | Path,
    *,
    tilesets_path: str | Path | None = None,
    tilemap_path: str = "assets/tilemaps/passability.json",
    collision_layer_id: str = "blocked",
    tile_size: int = 48,
    block_regions: Iterable[int] = (1,),
) -> dict[str, Any]:
    """Return a Mesh scene tilemap section aligned 1:1 with the MZ map grid."""
    map_path = Path(map_path)
    map_payload = load_rmmz_map(map_path)
    tileset_id = int(map_payload.get("tilesetId", 0))
    ts_path = Path(tilesets_path) if tilesets_path else map_path.parent / "Tilesets.json"
    tileset_payload = load_rmmz_tileset(ts_path, tileset_id)
    width, height, tiles = blocked_mask_from_rmmz_map(
        map_payload,
        tileset_payload,
        block_regions=block_regions,
    )
    return {
        "path": tilemap_path,
        "collision_layer_id": collision_layer_id,
        "width": width,
        "height": height,
        "tilewidth": tile_size,
        "tileheight": tile_size,
        "tile_layers": [
            {
                "id": collision_layer_id,
                "draw": False,
                "collision": True,
                "z": -200,
                "tiles": tiles,
            }
        ],
    }


def apply_tilemap_to_scene(scene_payload: dict[str, Any], tilemap: dict[str, Any]) -> dict[str, Any]:
    updated = dict(scene_payload)
    updated["tilemap"] = tilemap
    return updated


def summarize_rmmz_passability(
    map_path: str | Path,
    *,
    tilesets_path: str | Path | None = None,
    tile_size: int = 48,
    block_regions: Iterable[int] = (1,),
) -> dict[str, Any]:
    map_path = Path(map_path)
    map_payload = load_rmmz_map(map_path)
    tileset_id = int(map_payload.get("tilesetId", 0))
    ts_path = Path(tilesets_path) if tilesets_path else map_path.parent / "Tilesets.json"
    tileset_payload = load_rmmz_tileset(ts_path, tileset_id)
    width, height, tiles = blocked_mask_from_rmmz_map(
        map_payload,
        tileset_payload,
        block_regions=block_regions,
    )
    blocked = sum(1 for value in tiles if value)
    return {
        "map": str(map_path),
        "width": width,
        "height": height,
        "tileset_id": tileset_id,
        "tileset_name": tileset_payload.get("name"),
        "blocked_cells": blocked,
        "open_cells": len(tiles) - blocked,
        "tile_size_px": int(tile_size),
        "pixel_coverage": (width * int(tile_size), height * int(tile_size)),
    }
