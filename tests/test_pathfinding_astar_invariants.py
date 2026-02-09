"""
Invariant tests for A* pathfinding.

These tests verify structural properties that must hold for ANY valid path:
- Path is in-bounds
- Path never steps onto blocked tiles
- Path has valid adjacency (no teleporting)
- Path includes start and goal
"""
from __future__ import annotations

import random
from typing import Sequence

import pytest

from engine.pathfinding import NavGrid, astar


def assert_path_invariants(
    path: list[tuple[int, int]],
    grid: NavGrid,
    start: tuple[int, int],
    goal: tuple[int, int],
    diag: bool,
) -> None:
    """
    Assert that a non-empty path satisfies all invariants.
    
    Raises AssertionError with descriptive message on violation.
    """
    if not path:
        return  # Empty path (unreachable) is valid
    
    # Invariant 1: Path starts at start
    assert path[0] == start, (
        f"Path does not start at start position.\n"
        f"  Expected start: {start}\n"
        f"  Actual first:   {path[0]}"
    )
    
    # Invariant 2: Path ends at goal
    assert path[-1] == goal, (
        f"Path does not end at goal position.\n"
        f"  Expected goal: {goal}\n"
        f"  Actual last:   {path[-1]}"
    )
    
    # Invariant 3: All positions in-bounds
    for i, pos in enumerate(path):
        assert grid.in_bounds(pos), (
            f"Path step {i} is out of bounds.\n"
            f"  Position: {pos}\n"
            f"  Grid size: {grid.width}x{grid.height}"
        )
    
    # Invariant 4: All positions walkable
    for i, pos in enumerate(path):
        assert grid.is_walkable(pos), (
            f"Path step {i} is on a blocked tile.\n"
            f"  Position: {pos}"
        )
    
    # Invariant 5: Valid adjacency between consecutive steps
    for i in range(len(path) - 1):
        curr = path[i]
        next_pos = path[i + 1]
        dx = abs(next_pos[0] - curr[0])
        dy = abs(next_pos[1] - curr[1])
        
        if diag:
            # Diagonal allowed: max 1 step in each direction
            valid = dx <= 1 and dy <= 1 and (dx > 0 or dy > 0)
        else:
            # Cardinal only: exactly 1 step total
            valid = (dx == 1 and dy == 0) or (dx == 0 and dy == 1)
        
        assert valid, (
            f"Invalid adjacency between steps {i} and {i+1}.\n"
            f"  From: {curr}\n"
            f"  To:   {next_pos}\n"
            f"  Delta: ({dx}, {dy})\n"
            f"  Diagonal allowed: {diag}"
        )
    
    # Invariant 6: No duplicates (no cycles in optimal path)
    seen: set[tuple[int, int]] = set()
    for i, pos in enumerate(path):
        assert pos not in seen, (
            f"Path contains duplicate position at step {i}.\n"
            f"  Position: {pos}\n"
            f"  (Indicates cycle in path)"
        )
        seen.add(pos)


# Deterministic random seed for reproducibility
RANDOM_SEED = 42


def generate_random_grid(
    width: int,
    height: int,
    block_ratio: float,
    rng: random.Random,
) -> NavGrid:
    """Generate a random grid with specified block ratio."""
    blocked: set[int] = set()
    total = width * height
    for idx in range(total):
        if rng.random() < block_ratio:
            blocked.add(idx)
    return NavGrid(
        width=width,
        height=height,
        tile_w=16,
        tile_h=16,
        blocked=frozenset(blocked),
    )


def find_walkable_position(grid: NavGrid, rng: random.Random) -> tuple[int, int] | None:
    """Find a random walkable position in grid."""
    walkable = [
        (x, y)
        for y in range(grid.height)
        for x in range(grid.width)
        if grid.is_walkable((x, y))
    ]
    if not walkable:
        return None
    return rng.choice(walkable)


@pytest.mark.parametrize("seed_offset", range(10))
def test_astar_invariants_random_grids_cardinal(seed_offset: int) -> None:
    """Test invariants on randomly generated grids (cardinal movement)."""
    rng = random.Random(RANDOM_SEED + seed_offset)
    
    for _ in range(5):
        width = rng.randint(5, 20)
        height = rng.randint(5, 20)
        block_ratio = rng.uniform(0.1, 0.4)
        
        grid = generate_random_grid(width, height, block_ratio, rng)
        start = find_walkable_position(grid, rng)
        goal = find_walkable_position(grid, rng)
        
        if start is None or goal is None:
            continue
        
        path = astar(start, goal, grid, diag=False)
        assert_path_invariants(path, grid, start, goal, diag=False)


@pytest.mark.parametrize("seed_offset", range(10))
def test_astar_invariants_random_grids_diagonal(seed_offset: int) -> None:
    """Test invariants on randomly generated grids (diagonal movement)."""
    rng = random.Random(RANDOM_SEED + seed_offset)
    
    for _ in range(5):
        width = rng.randint(5, 20)
        height = rng.randint(5, 20)
        block_ratio = rng.uniform(0.1, 0.4)
        
        grid = generate_random_grid(width, height, block_ratio, rng)
        start = find_walkable_position(grid, rng)
        goal = find_walkable_position(grid, rng)
        
        if start is None or goal is None:
            continue
        
        path = astar(start, goal, grid, diag=True)
        assert_path_invariants(path, grid, start, goal, diag=True)


def test_astar_invariants_empty_grid() -> None:
    """Test invariants on fully walkable grid."""
    grid = NavGrid(width=10, height=10, tile_w=16, tile_h=16, blocked=frozenset())
    
    test_cases = [
        ((0, 0), (9, 9)),
        ((0, 0), (0, 0)),
        ((5, 5), (0, 0)),
        ((0, 9), (9, 0)),
    ]
    
    for start, goal in test_cases:
        for diag in [False, True]:
            path = astar(start, goal, grid, diag=diag)
            assert_path_invariants(path, grid, start, goal, diag=diag)


def test_astar_invariants_corridor() -> None:
    """Test invariants on narrow corridor."""
    # Create a corridor: only row 2 is walkable
    width, height = 10, 5
    blocked = {
        y * width + x
        for y in range(height)
        for x in range(width)
        if y != 2
    }
    grid = NavGrid(
        width=width,
        height=height,
        tile_w=16,
        tile_h=16,
        blocked=frozenset(blocked),
    )
    
    start = (0, 2)
    goal = (9, 2)
    path = astar(start, goal, grid, diag=False)
    
    assert_path_invariants(path, grid, start, goal, diag=False)
    # Additionally check path length for this specific case
    assert len(path) == 10, f"Corridor path should be 10 steps, got {len(path)}"


def test_astar_invariants_spiral() -> None:
    """Test invariants on spiral maze."""
    # Create a simple spiral-like structure
    grid_str = """
..........
.########.
.#......#.
.#.####.#.
.#.#..#.#.
.#.#..#.#.
.#.####.#.
.#......#.
.########.
..........
"""
    lines = [line for line in grid_str.strip().split("\n")]
    height = len(lines)
    width = len(lines[0])
    
    blocked: set[int] = set()
    for y, line in enumerate(lines):
        for x, ch in enumerate(line):
            if ch == '#':
                blocked.add(y * width + x)
    
    grid = NavGrid(
        width=width,
        height=height,
        tile_w=16,
        tile_h=16,
        blocked=frozenset(blocked),
    )
    
    # Path from outside spiral to inside
    start = (0, 0)
    goal = (4, 4)  # Inside the spiral
    
    path = astar(start, goal, grid, diag=False)
    assert_path_invariants(path, grid, start, goal, diag=False)
