from __future__ import annotations


def test_astar_routes_through_single_gap_wall() -> None:
    from engine.pathfinding import NavGrid, astar

    width, height = 5, 5
    tile_w, tile_h = 16, 16

    # Block column x=1 for all rows except y=2 (single gap).
    blocked = {y * width + 1 for y in range(height) if y != 2}
    grid = NavGrid(width=width, height=height, tile_w=tile_w, tile_h=tile_h, blocked=frozenset(blocked))

    start = (0, 2)
    goal = (4, 2)
    path = astar(start, goal, grid, diag=False)

    assert path == [(0, 2), (1, 2), (2, 2), (3, 2), (4, 2)]

