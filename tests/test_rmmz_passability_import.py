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

RMMZ_MAP002 = Path(r"C:/Users/slebb/Documents/RMMZ/light test/data/Map002.json")
RMMZ_TILESETS = Path(r"C:/Users/slebb/Documents/RMMZ/light test/data/Tilesets.json")

pytestmark = pytest.mark.fast


@pytest.mark.skipif(not RMMZ_MAP002.is_file(), reason="RMMZ light test project not available")
def test_map002_passability_summary_matches_known_counts() -> None:
    summary = summarize_rmmz_passability(RMMZ_MAP002, tilesets_path=RMMZ_TILESETS)
    assert summary["width"] == 29
    assert summary["height"] == 24
    assert summary["blocked_cells"] == 324
    assert summary["open_cells"] == 372
    assert summary["tileset_name"] == "Outside"


@pytest.mark.skipif(not RMMZ_MAP002.is_file(), reason="RMMZ light test project not available")
def test_mesh_tilemap_grid_matches_rmmz_dimensions() -> None:
    tilemap = mesh_tilemap_from_rmmz_map(RMMZ_MAP002, tilesets_path=RMMZ_TILESETS)
    assert tilemap["width"] == 29
    assert tilemap["height"] == 24
    assert tilemap["tilewidth"] == 48
    assert tilemap["tileheight"] == 48
    layer = tilemap["tile_layers"][0]
    assert layer["id"] == "blocked"
    assert layer["draw"] is False
    assert layer["collision"] is True
    assert len(layer["tiles"]) == 29 * 24
    assert sum(layer["tiles"]) == 324


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
