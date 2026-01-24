from __future__ import annotations

from .nav_grid import NavGrid, TileCoord


def raycast_tiles(start: TileCoord, goal: TileCoord) -> list[TileCoord]:
    """
    Deterministic Bresenham raycast from start->goal, inclusive.

    Returns a list of tiles in traversal order.
    """
    x0, y0 = start
    x1, y1 = goal
    x0 = int(x0)
    y0 = int(y0)
    x1 = int(x1)
    y1 = int(y1)

    tiles: list[TileCoord] = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    while True:
        tiles.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy
    return tiles


def line_of_sight_clear(start: TileCoord, goal: TileCoord, grid: NavGrid) -> bool:
    """
    Return True if the straight line between start and goal crosses only walkable tiles.

    Excludes the start tile from blocking checks but includes the goal tile.
    """
    if not grid.in_bounds(start) or not grid.in_bounds(goal):
        return False
    tiles = raycast_tiles(start, goal)
    if not tiles:
        return False
    for tile in tiles[1:]:
        if not grid.is_walkable(tile):
            return False
    return True

