"""
Golden-fixture tests for A* pathfinding using ASCII maps.

Map legend:
  '.' = walkable
  '#' = blocked
  'S' = start (walkable)
  'G' = goal (walkable)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import pytest

from engine.pathfinding import NavGrid, astar


@dataclass(frozen=True)
class AsciiMapCase:
    """A test case with ASCII map input and expected path."""
    name: str
    ascii_map: str
    diag: bool
    expected_path: list[tuple[int, int]]  # [(x, y), ...]


def parse_ascii_map(ascii_map: str) -> tuple[NavGrid, tuple[int, int], tuple[int, int]]:
    """
    Parse an ASCII map and return (grid, start, goal).
    
    Grid coordinate system: (0, 0) is top-left, x increases right, y increases down.
    """
    lines = [line for line in ascii_map.strip().split("\n")]
    height = len(lines)
    width = max(len(line) for line in lines) if lines else 0

    blocked: set[int] = set()
    start: tuple[int, int] | None = None
    goal: tuple[int, int] | None = None

    for y, line in enumerate(lines):
        for x, ch in enumerate(line):
            idx = y * width + x
            if ch == '#':
                blocked.add(idx)
            elif ch == 'S':
                start = (x, y)
            elif ch == 'G':
                goal = (x, y)
            elif ch == 'X':
                # X marks both start and goal (same position)
                start = (x, y)
                goal = (x, y)
            elif ch == '.':
                pass
            else:
                # Unknown char treated as walkable
                pass

    if start is None:
        raise ValueError("No start 'S' or 'X' found in map")
    if goal is None:
        raise ValueError("No goal 'G' or 'X' found in map")

    grid = NavGrid(
        width=width,
        height=height,
        tile_w=16,
        tile_h=16,
        blocked=frozenset(blocked),
    )
    return grid, start, goal


# Golden test cases
GOLDEN_CASES: Sequence[AsciiMapCase] = [
    AsciiMapCase(
        name="straight_line_horizontal",
        ascii_map="""
S....G
""",
        diag=False,
        expected_path=[(0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (5, 0)],
    ),
    AsciiMapCase(
        name="straight_line_vertical",
        ascii_map="""
S
.
.
G
""",
        diag=False,
        expected_path=[(0, 0), (0, 1), (0, 2), (0, 3)],
    ),
    AsciiMapCase(
        name="simple_obstacle_around",
        ascii_map="""
S.#..
..#..
..#..
.....
G....
""",
        diag=False,
        expected_path=[(0, 0), (0, 1), (0, 2), (0, 3), (0, 4)],
    ),
    AsciiMapCase(
        name="wall_with_gap",
        ascii_map="""
S.###
..#..
..#..
.....
G....
""",
        diag=False,
        expected_path=[(0, 0), (0, 1), (0, 2), (0, 3), (0, 4)],
    ),
    AsciiMapCase(
        name="maze_simple",
        ascii_map="""
S.#G
..#.
....
""",
        diag=False,
        # Path goes down then right and up - actual astar tie-breaking order
        expected_path=[(0, 0), (1, 0), (1, 1), (1, 2), (2, 2), (3, 2), (3, 1), (3, 0)],
    ),
    AsciiMapCase(
        name="same_position",
        ascii_map="""
X
""",
        diag=False,
        expected_path=[(0, 0)],
    ),
    AsciiMapCase(
        name="adjacent_horizontal",
        ascii_map="""
SG
""",
        diag=False,
        expected_path=[(0, 0), (1, 0)],
    ),
    AsciiMapCase(
        name="adjacent_vertical",
        ascii_map="""
S
G
""",
        diag=False,
        expected_path=[(0, 0), (0, 1)],
    ),
    AsciiMapCase(
        name="diagonal_straight",
        ascii_map="""
S....
.....
.....
....G
""",
        diag=True,
        # Actual astar diagonal path with tie-breaking
        expected_path=[(0, 0), (1, 0), (2, 1), (3, 2), (4, 3)],
    ),
    AsciiMapCase(
        name="corner_obstacle",
        ascii_map="""
S##
.#.
..G
""",
        diag=False,
        expected_path=[(0, 0), (0, 1), (0, 2), (1, 2), (2, 2)],
    ),
]


@pytest.mark.parametrize(
    "case",
    GOLDEN_CASES,
    ids=lambda c: c.name,
)
def test_astar_golden(case: AsciiMapCase) -> None:
    """Test A* against golden expected paths."""
    grid, start, goal = parse_ascii_map(case.ascii_map)

    # For same_position case, S is also G
    if case.name == "same_position":
        goal = start

    path = astar(start, goal, grid, diag=case.diag)
    assert path == case.expected_path, (
        f"Path mismatch for {case.name}:\n"
        f"  Expected: {case.expected_path}\n"
        f"  Got:      {path}"
    )


# Unreachable cases
UNREACHABLE_CASES: Sequence[tuple[str, str, bool]] = [
    # Note: For testing blocked start/goal, we test via the astar bounds check,
    # since the ASCII parser can't have S/G and # at the same position
    (
        "surrounded_goal",
        """
S....
.###.
.#G#.
.###.
.....
""",
        False,
    ),
    (
        "surrounded_start",
        """
###..
#S#..
###..
....G
""",
        False,
    ),
    (
        "wall_divides_completely",
        """
S.#.G
..#..
..#..
..#..
..#..
""",
        False,
    ),
]


@pytest.mark.parametrize(
    "name,ascii_map,diag",
    UNREACHABLE_CASES,
    ids=lambda x: x if isinstance(x, str) else None,
)
def test_astar_unreachable(name: str, ascii_map: str, diag: bool) -> None:
    """Test that A* returns empty path for unreachable goals."""
    grid, start, goal = parse_ascii_map(ascii_map)

    # For blocked_goal/blocked_start, the S or G is on a '#'
    if name == "blocked_goal":
        goal = (2, 2)  # The '#' position
    elif name == "blocked_start":
        start = (0, 0)  # The '#' position

    path = astar(start, goal, grid, diag=diag)
    assert path == [], f"Expected empty path for unreachable case '{name}', got {path}"


def test_astar_out_of_bounds_start() -> None:
    """Test that out-of-bounds start returns empty path."""
    grid = NavGrid(width=5, height=5, tile_w=16, tile_h=16, blocked=frozenset())
    path = astar((-1, 0), (2, 2), grid, diag=False)
    assert path == []


def test_astar_out_of_bounds_goal() -> None:
    """Test that out-of-bounds goal returns empty path."""
    grid = NavGrid(width=5, height=5, tile_w=16, tile_h=16, blocked=frozenset())
    path = astar((0, 0), (10, 10), grid, diag=False)
    assert path == []


def test_astar_blocked_start() -> None:
    """Test that blocked start returns empty path."""
    # Block tile at (0, 0), which is index 0 in a 5x5 grid
    grid = NavGrid(width=5, height=5, tile_w=16, tile_h=16, blocked=frozenset({0}))
    path = astar((0, 0), (2, 2), grid, diag=False)
    assert path == []


def test_astar_blocked_goal() -> None:
    """Test that blocked goal returns empty path."""
    # Block tile at (2, 2), which is index 2*5 + 2 = 12
    grid = NavGrid(width=5, height=5, tile_w=16, tile_h=16, blocked=frozenset({12}))
    path = astar((0, 0), (2, 2), grid, diag=False)
    assert path == []
