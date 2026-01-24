from __future__ import annotations

import heapq
from dataclasses import dataclass

from .nav_grid import NavGrid, TileCoord


@dataclass(slots=True)
class _Node:
    f: int
    g: int
    h: int
    pos: TileCoord


def _heuristic(a: TileCoord, b: TileCoord, *, diag: bool) -> int:
    ax, ay = a
    bx, by = b
    dx = abs(ax - bx)
    dy = abs(ay - by)
    if not diag:
        return 10 * (dx + dy)
    # Octile distance with 10/14 costs.
    return 10 * (dx + dy) + (14 - 2 * 10) * min(dx, dy)


def astar(
    start: TileCoord,
    goal: TileCoord,
    grid: NavGrid,
    *,
    diag: bool = False,
) -> list[TileCoord]:
    """
    Deterministic A* path on a NavGrid.

    Returns a list of tile coordinates (x,y), including both start and goal,
    or an empty list when no path exists / inputs invalid.
    """
    if not grid.in_bounds(start) or not grid.in_bounds(goal):
        return []
    if not grid.is_walkable(start) or not grid.is_walkable(goal):
        return []
    if start == goal:
        return [start]

    # Deterministic neighbor ordering.
    if diag:
        neighbor_steps: tuple[tuple[int, int], ...] = (
            (1, 0),
            (-1, 0),
            (0, 1),
            (0, -1),
            (1, 1),
            (1, -1),
            (-1, 1),
            (-1, -1),
        )
    else:
        neighbor_steps = ((1, 0), (-1, 0), (0, 1), (0, -1))

    open_heap: list[tuple[int, int, int, int]] = []
    came_from: dict[TileCoord, TileCoord] = {}
    g_score: dict[TileCoord, int] = {start: 0}

    h0 = _heuristic(start, goal, diag=diag)
    heapq.heappush(open_heap, (h0, 0, start[1], start[0]))

    while open_heap:
        _f, g, cy, cx = heapq.heappop(open_heap)
        current = (cx, cy)

        if current == goal:
            path: list[TileCoord] = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path

        if g != g_score.get(current, 0):
            continue

        for dx, dy in neighbor_steps:
            nx, ny = cx + dx, cy + dy
            neighbor = (nx, ny)
            if not grid.in_bounds(neighbor) or not grid.is_walkable(neighbor):
                continue

            step_cost = 14 if (dx != 0 and dy != 0) else 10
            tentative_g = g + step_cost
            best_g = g_score.get(neighbor)
            if best_g is not None and tentative_g >= best_g:
                continue

            came_from[neighbor] = current
            g_score[neighbor] = tentative_g
            h = _heuristic(neighbor, goal, diag=diag)
            f = tentative_g + h
            # Deterministic tie-break: (f, g, y, x)
            heapq.heappush(open_heap, (f, tentative_g, ny, nx))

    return []

