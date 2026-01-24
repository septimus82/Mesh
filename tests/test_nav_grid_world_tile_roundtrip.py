from __future__ import annotations


def test_nav_grid_world_tile_roundtrip_center_of_tile() -> None:
    from engine.pathfinding import NavGrid

    grid = NavGrid(width=10, height=10, tile_w=16, tile_h=16, blocked=frozenset())

    for tile in ((0, 0), (1, 2), (9, 9), (5, 3)):
        wx, wy = grid.tile_center_world(tile)
        assert grid.world_to_tile(wx, wy) == tile
        wx2, wy2 = grid.tile_center_world(grid.world_to_tile(wx, wy))
        assert abs(wx2 - wx) < 1e-6
        assert abs(wy2 - wy) < 1e-6

