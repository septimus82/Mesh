import pytest

from engine.tilemap_flood_fill import FloodFillMaxTilesExceeded, flood_fill_indices


def test_tilemap_flood_fill_math_4_neighbor_basic_indices_order():
    # 4x4 all zeros, start at (0,0), BFS deterministic neighbor order R,L,D,U.
    w, h = 4, 4
    tiles = [0] * (w * h)
    indices = flood_fill_indices(tiles, w, h, 0, 0, 0, diag=False, max_tiles=100)
    assert indices[:5] == [0, 1, 4, 2, 5]


def test_tilemap_flood_fill_math_8_neighbor_includes_diagonal_connections():
    # 2x2:
    # 0 1
    # 1 0
    w, h = 2, 2
    tiles = [0, 1, 1, 0]
    indices4 = flood_fill_indices(tiles, w, h, 0, 0, 0, diag=False, max_tiles=10)
    indices8 = flood_fill_indices(tiles, w, h, 0, 0, 0, diag=True, max_tiles=10)
    assert indices4 == [0]
    assert indices8 == [0, 3]


def test_tilemap_flood_fill_math_max_tiles_exceeded_surfaces_partial():
    w, h = 4, 4
    tiles = [0] * (w * h)
    with pytest.raises(FloodFillMaxTilesExceeded) as excinfo:
        flood_fill_indices(tiles, w, h, 0, 0, 0, diag=False, max_tiles=5)
    err = excinfo.value
    assert err.max_tiles == 5
    assert err.attempted == 6
    assert err.partial_indices == [0, 1, 4, 2, 5]
