"""Tests for RMMZ → Mesh passability import."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.tooling.rmmz_passability import (
    blocked_mask_from_rmmz_map,
    mesh_tilemap_from_rmmz_map,
    summarize_rmmz_passability,
)

# The owner's own RPG Maker project, used only as an optional real-data smoke check. It is edited over
# time, so nothing here asserts its exact counts (they asserted 324 blocked cells; the map now has 323).
RMMZ_MAP002 = Path(r"C:/Users/slebb/Documents/RMMZ/light test/data/Map002.json")
RMMZ_TILESETS = Path(r"C:/Users/slebb/Documents/RMMZ/light test/data/Tilesets.json")

pytestmark = pytest.mark.fast


def _write_map_project(root: Path) -> tuple[Path, Path, int]:
    """A 29x24 map in RPG Maker MZ's file format, with a known number of blocked cells.

    Blocking comes from every path the importer has: a fully impassable tile on layer 0, on an upper
    layer, and region 1. A partly passable tile (some direction bits only) and region 2 must not block.
    The map names tileset 2; tileset 1 would block nothing, so picking the wrong one would show.
    """
    width, height = 29, 24
    cells = width * height
    data = [0] * (cells * 6)
    wall, partial, decor = 10, 11, 12
    blocked = set()
    for x in range(width):  # a wall along the top row, on layer 0
        data[x] = wall
        blocked.add((x, 0))
    for y in range(5, 15):  # a column of impassable decoration on layer 3
        data[3 * cells + y * width + 7] = decor
        blocked.add((7, y))
    for x in range(10, 20):  # region 1 along row 20 blocks; region 2 along row 21 doesn't
        data[5 * cells + 20 * width + x] = 1
        data[5 * cells + 21 * width + x] = 2
        blocked.add((x, 20))
    for x in range(0, 29, 3):  # partly passable tiles (only some direction bits) never block
        data[2 * cells + 22 * width + x] = partial
    flags = [0] * 32
    flags[wall], flags[partial], flags[decor] = 0x0F, 0x05, 0x0F
    map_path, tilesets_path = root / "Map002.json", root / "Tilesets.json"
    map_path.write_text(json.dumps({"width": width, "height": height, "tilesetId": 2, "data": data}), encoding="utf-8")
    tilesets_path.write_text(json.dumps([None, {"name": "Nothing blocks", "flags": [0] * 32},
                                         {"name": "Outside", "flags": flags}]), encoding="utf-8")
    return map_path, tilesets_path, len(blocked)


def test_map_file_summary_counts_every_blocking_rule(tmp_path: Path) -> None:
    map_path, tilesets_path, blocked = _write_map_project(tmp_path)
    summary = summarize_rmmz_passability(map_path, tilesets_path=tilesets_path)
    assert (summary["width"], summary["height"]) == (29, 24)
    assert summary["blocked_cells"] == blocked == 29 + 10 + 10
    assert summary["open_cells"] == 29 * 24 - blocked
    assert summary["tileset_name"] == "Outside"


def test_mesh_tilemap_from_a_map_file_matches_its_grid(tmp_path: Path) -> None:
    map_path, tilesets_path, blocked = _write_map_project(tmp_path)
    tilemap = mesh_tilemap_from_rmmz_map(map_path, tilesets_path=tilesets_path)
    assert (tilemap["width"], tilemap["height"], tilemap["tilewidth"], tilemap["tileheight"]) == (29, 24, 48, 48)
    layer = tilemap["tile_layers"][0]
    assert (layer["id"], layer["draw"], layer["collision"]) == ("blocked", False, True)
    assert len(layer["tiles"]) == 29 * 24 and sum(layer["tiles"]) == blocked
    assert layer["tiles"][0] == 1 and layer["tiles"][21 * 29 + 12] == 0  # row 0 wall; region 2 open


@pytest.mark.skipif(not RMMZ_MAP002.is_file(), reason="optional: the owner's RMMZ 'light test' project is not on this machine")
def test_the_owners_real_map_imports_consistently() -> None:
    summary = summarize_rmmz_passability(RMMZ_MAP002, tilesets_path=RMMZ_TILESETS)
    tilemap = mesh_tilemap_from_rmmz_map(RMMZ_MAP002, tilesets_path=RMMZ_TILESETS)
    tiles = tilemap["tile_layers"][0]["tiles"]
    assert len(tiles) == summary["width"] * summary["height"]
    assert sum(tiles) == summary["blocked_cells"] and summary["blocked_cells"] + summary["open_cells"] == len(tiles)


def test_blocked_mask_small_fixture() -> None:
    map_payload = {
        "width": 2,
        "height": 2,
        "data": [
            # layer 0
            10, 0,
            0, 0,
            # layers 1-4 empty
            0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
            0, 0, 0, 0, 0, 0, 0, 0,
            # layer 5 regions
            1, 0,
            0, 0,
        ],
    }
    flags = [0] * 20
    flags[10] = 0x0F
    width, height, tiles = blocked_mask_from_rmmz_map(map_payload, {"flags": flags})
    assert (width, height) == (2, 2)
    assert tiles == [1, 0, 0, 0]


def test_summary_uses_requested_tile_size(tmp_path: Path) -> None:
    map_path = tmp_path / "Map001.json"
    tilesets_path = tmp_path / "Tilesets.json"
    map_path.write_text(
        json.dumps(
            {
                "width": 2,
                "height": 3,
                "tilesetId": 1,
                "data": [0] * (2 * 3 * 6),
            }
        ),
        encoding="utf-8",
    )
    tilesets_path.write_text(
        json.dumps([None, {"name": "Fixture", "flags": [0]}]),
        encoding="utf-8",
    )

    summary = summarize_rmmz_passability(
        map_path,
        tilesets_path=tilesets_path,
        tile_size=32,
    )

    assert summary["tile_size_px"] == 32
    assert summary["pixel_coverage"] == (64, 96)
