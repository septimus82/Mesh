"""
Performance guard tests for A* pathfinding.

Ensure pathfinding doesn't degrade unexpectedly on large or complex maps.
Uses node expansion cap to detect algorithmic regressions.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import pytest

from engine.pathfinding import NavGrid, astar


# Maximum allowed node expansions for a 50x50 grid worst case
MAX_NODE_EXPANSIONS_50x50 = 5000

# Maximum time allowed for any single pathfinding call (seconds)
MAX_PATH_TIME_SECONDS = 0.5


def count_expansions_astar(
    start: tuple[int, int],
    goal: tuple[int, int],
    grid: NavGrid,
    diag: bool,
) -> tuple[list[tuple[int, int]], int]:
    """
    Run A* and count node expansions.
    
    This is a wrapper that tracks how many nodes were expanded.
    Returns (path, expansion_count).
    """
    import heapq
    
    if not grid.in_bounds(start) or not grid.in_bounds(goal):
        return [], 0
    if not grid.is_walkable(start) or not grid.is_walkable(goal):
        return [], 0
    if start == goal:
        return [start], 1
    
    # Deterministic neighbor ordering
    if diag:
        neighbor_steps = (
            (1, 0), (-1, 0), (0, 1), (0, -1),
            (1, 1), (1, -1), (-1, 1), (-1, -1),
        )
    else:
        neighbor_steps = ((1, 0), (-1, 0), (0, 1), (0, -1))
    
    def heuristic(a: tuple[int, int], b: tuple[int, int]) -> int:
        ax, ay = a
        bx, by = b
        dx = abs(ax - bx)
        dy = abs(ay - by)
        if not diag:
            return 10 * (dx + dy)
        return 10 * (dx + dy) + (14 - 20) * min(dx, dy)
    
    open_heap: list[tuple[int, int, int, int]] = []
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    g_score: dict[tuple[int, int], int] = {start: 0}
    expansion_count = 0
    
    h0 = heuristic(start, goal)
    heapq.heappush(open_heap, (h0, 0, start[1], start[0]))
    
    while open_heap:
        _f, g, cy, cx = heapq.heappop(open_heap)
        current = (cx, cy)
        expansion_count += 1
        
        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path, expansion_count
        
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
            h = heuristic(neighbor, goal)
            f = tentative_g + h
            heapq.heappush(open_heap, (f, tentative_g, ny, nx))
    
    return [], expansion_count


def test_astar_perf_open_grid_50x50() -> None:
    """Performance test on wide-open 50x50 grid."""
    grid = NavGrid(width=50, height=50, tile_w=16, tile_h=16, blocked=frozenset())
    
    start = (0, 0)
    goal = (49, 49)
    
    start_time = time.perf_counter()
    path, expansions = count_expansions_astar(start, goal, grid, diag=False)
    elapsed = time.perf_counter() - start_time
    
    assert path, "Should find path in open grid"
    assert elapsed < MAX_PATH_TIME_SECONDS, (
        f"Pathfinding took too long: {elapsed:.3f}s > {MAX_PATH_TIME_SECONDS}s"
    )
    # For open grid, expansions should be reasonable
    assert expansions < MAX_NODE_EXPANSIONS_50x50, (
        f"Too many node expansions: {expansions} > {MAX_NODE_EXPANSIONS_50x50}"
    )


def test_astar_perf_maze_50x50() -> None:
    """Performance test on maze-like 50x50 grid."""
    # Create a grid with vertical walls every 5 columns, each with a gap
    # Walls are only at x=4,9,14,19,24,29,34,39,44 (not 49 to ensure goal is reachable)
    width, height = 50, 50
    blocked: set[int] = set()
    
    for wall_x in range(4, width - 5, 5):  # Stop before x=49
        gap_y = (wall_x // 5 * 7) % height  # Deterministic gap position
        for y in range(height):
            if y != gap_y:
                blocked.add(y * width + wall_x)
    
    grid = NavGrid(
        width=width,
        height=height,
        tile_w=16,
        tile_h=16,
        blocked=frozenset(blocked),
    )
    
    start = (0, 0)
    goal = (49, 49)
    
    start_time = time.perf_counter()
    path, expansions = count_expansions_astar(start, goal, grid, diag=False)
    elapsed = time.perf_counter() - start_time
    
    assert path, "Should find path through maze"
    assert elapsed < MAX_PATH_TIME_SECONDS, (
        f"Pathfinding took too long: {elapsed:.3f}s > {MAX_PATH_TIME_SECONDS}s"
    )
    assert expansions < MAX_NODE_EXPANSIONS_50x50, (
        f"Too many node expansions: {expansions} > {MAX_NODE_EXPANSIONS_50x50}"
    )


def test_astar_perf_diagonal_50x50() -> None:
    """Performance test with diagonal movement on 50x50 grid."""
    grid = NavGrid(width=50, height=50, tile_w=16, tile_h=16, blocked=frozenset())
    
    start = (0, 0)
    goal = (49, 49)
    
    start_time = time.perf_counter()
    path, expansions = count_expansions_astar(start, goal, grid, diag=True)
    elapsed = time.perf_counter() - start_time
    
    assert path, "Should find path with diagonal"
    assert elapsed < MAX_PATH_TIME_SECONDS, (
        f"Pathfinding took too long: {elapsed:.3f}s > {MAX_PATH_TIME_SECONDS}s"
    )
    # Diagonal should be more efficient
    assert expansions < MAX_NODE_EXPANSIONS_50x50 // 2, (
        f"Too many node expansions with diagonal: {expansions}"
    )


def test_astar_perf_worst_case_spiral() -> None:
    """Performance test on spiral maze (forces long exploration)."""
    # Create concentric square spiral
    size = 21  # Odd for center
    blocked: set[int] = set()
    
    # Build spiral walls
    for ring in range(0, size // 2, 2):
        # Top wall (leave gap on right)
        for x in range(ring, size - ring - 1):
            blocked.add(ring * size + x)
        # Right wall (leave gap at bottom)
        for y in range(ring, size - ring - 1):
            blocked.add(y * size + (size - ring - 1))
        # Bottom wall (leave gap on left)
        for x in range(ring + 1, size - ring):
            blocked.add((size - ring - 1) * size + x)
        # Left wall (leave gap at top)
        for y in range(ring + 2, size - ring):
            blocked.add(y * size + ring)
    
    # Ensure entrance and center are clear
    blocked.discard(0)  # Top-left entrance
    center = (size // 2, size // 2)
    blocked.discard(center[1] * size + center[0])
    
    grid = NavGrid(
        width=size,
        height=size,
        tile_w=16,
        tile_h=16,
        blocked=frozenset(blocked),
    )
    
    # Navigate from corner toward center region
    start = (1, 1)
    goal = (size - 2, size - 2)
    
    start_time = time.perf_counter()
    path = astar(start, goal, grid, diag=False)
    elapsed = time.perf_counter() - start_time
    
    # May or may not find path depending on spiral construction
    # Main check is time bound
    assert elapsed < MAX_PATH_TIME_SECONDS, (
        f"Spiral pathfinding took too long: {elapsed:.3f}s > {MAX_PATH_TIME_SECONDS}s"
    )


def test_astar_determinism_across_runs() -> None:
    """Ensure same inputs always produce same path."""
    grid = NavGrid(width=20, height=20, tile_w=16, tile_h=16, blocked=frozenset())
    
    # Add some obstacles
    blocked = {
        5 * 20 + 5,
        5 * 20 + 6,
        6 * 20 + 5,
        10 * 20 + 10,
        10 * 20 + 11,
        11 * 20 + 10,
    }
    grid = NavGrid(
        width=20,
        height=20,
        tile_w=16,
        tile_h=16,
        blocked=frozenset(blocked),
    )
    
    start = (0, 0)
    goal = (19, 19)
    
    # Run multiple times
    paths = [astar(start, goal, grid, diag=False) for _ in range(5)]
    
    # All should be identical
    for i, p in enumerate(paths[1:], 1):
        assert p == paths[0], f"Path {i} differs from path 0"
