"""Performance guards for the game's A* search, ``engine.pathfinding.astar`` (#422).

Every check here runs the production function. (Until #422's A* correction three of the four timed tests ran a copy of
the algorithm kept in this file, and all four judged one unrepeated wall-clock sample against a fixed 0.5 s: a search
that takes 5-8 ms failed at 0.547 s on a CI runner that stalled once.) Two guards, kept apart:

* **Work, exact.** A stand-in for the grid counts what ``astar`` asks of it: one bounds question per neighbour of each
  tile it expands, so the count is the search's work, the same on every machine. Each scenario's count may not rise
  above today's (``Scenario.expanded``), and no tile may be expanded twice. The route itself is checked too: it
  exists, starts and ends where asked, crosses only walkable tiles by legal steps, is a shortest one, and is the same
  route every time.
* **Runtime, coarse and runner-relative.** The time one neighbour probe costs, as a fraction of the repository's
  calibration loop (``tooling.runner_calibration.cpu_ms``, the fixed pure-Python work the terrain gate also measures
  runners with), from medians of interleaved samples: a runner that is slow, busy or stalls for one sample slows
  both sides or neither. ``MAX_PROBE_COST`` is about four times today's cost: it catches a search made several times
  slower per unit of work (which the count can't see), not a small drift.

The last tests break the search on purpose (through ``monkeypatch``, never in the engine) and expect these checks to
fail: a guard nothing can trip protects nothing."""

from __future__ import annotations

import importlib
import statistics
import time
import types
from dataclasses import dataclass
from typing import Any, cast

import pytest

from engine.pathfinding import NavGrid, astar
from tests.test_pathfinding_astar_invariants import assert_path_invariants
from tooling.runner_calibration import cpu_ms

Tile = tuple[int, int]

# The most one neighbour probe may cost, in millionths of one calibration loop. Measured: 27-48 as a rule and never
# over 54 in 280 runs (Python 3.10 and 3.13, idle and with every core busy); a search made 3.5-5 times slower crosses
# it every time.
# The evidence, and what this can't see, is in docs/reviews/astar_perf_guard.md.
MAX_PROBE_COST = 150.0


@dataclass(frozen=True)
class Scenario:
    grid: NavGrid
    start: Tile
    goal: Tile
    diag: bool
    tiles: int  # tiles in a shortest route, both ends included
    expanded: int  # the work budget: tiles the search expands today
    repeat: int  # searches per timed sample, so a sample is a few milliseconds


def _grid(size: int, blocked: set[int]) -> NavGrid:
    return NavGrid(width=size, height=size, tile_w=16, tile_h=16, blocked=frozenset(blocked))


def _maze() -> NavGrid:
    """Vertical walls every 5 columns (x = 4, 9 ... 44), each with one gap."""
    blocked: set[int] = set()
    for wall_x in range(4, 45, 5):
        gap_y = (wall_x // 5 * 7) % 50
        blocked |= {y * 50 + wall_x for y in range(50) if y != gap_y}
    return _grid(50, blocked)


def _spiral() -> NavGrid:
    """Concentric square walls, each open at one corner."""
    size = 21
    blocked: set[int] = set()
    for ring in range(0, size // 2, 2):
        blocked |= {ring * size + x for x in range(ring, size - ring - 1)}  # top
        blocked |= {y * size + (size - ring - 1) for y in range(ring, size - ring - 1)}  # right
        blocked |= {(size - ring - 1) * size + x for x in range(ring + 1, size - ring)}  # bottom
        blocked |= {y * size + ring for y in range(ring + 2, size - ring)}  # left
    blocked.discard(0)
    blocked.discard((size // 2) * size + size // 2)
    return _grid(size, blocked)


_OPEN = _grid(50, set())
SCENARIOS = {
    # Corner to corner over open ground: every tile lies on some shortest route, so the search floods the grid.
    "open": Scenario(_OPEN, (0, 0), (49, 49), diag=False, tiles=99, expanded=2499, repeat=1),
    "maze": Scenario(_maze(), (0, 0), (49, 49), diag=False, tiles=185, expanded=2004, repeat=1),
    # The two where the heuristic does the work: only the tiles of the straight line are expanded.
    "diagonal": Scenario(_OPEN, (0, 0), (49, 49), diag=True, tiles=50, expanded=49, repeat=16),
    "straight": Scenario(_OPEN, (0, 25), (49, 25), diag=False, tiles=50, expanded=49, repeat=16),
    "spiral": Scenario(_spiral(), (1, 1), (19, 19), diag=False, tiles=37, expanded=204, repeat=12),
}


class _Watched:
    """Stands in for a NavGrid: answers as it does, and counts the bounds questions ``astar`` asks."""

    def __init__(self, grid: NavGrid) -> None:
        self._grid, self.asked = grid, 0

    def in_bounds(self, pos: Tile) -> bool:
        self.asked += 1
        return self._grid.in_bounds(pos)

    def is_walkable(self, pos: Tile) -> bool:
        return self._grid.is_walkable(pos)


def _search(s: Scenario) -> tuple[list[Tile], int]:
    """The production search's route and how many tiles it expanded."""
    watched = _Watched(s.grid)
    path = astar(s.start, s.goal, cast(NavGrid, watched), diag=s.diag)
    probes, neighbours = watched.asked - 2, 8 if s.diag else 4  # (the start and the goal are asked once each first)
    assert probes % neighbours == 0, "astar no longer asks the grid once per neighbour: count its work another way"
    return path, probes // neighbours


def _check_route(path: list[Tile], s: Scenario) -> None:
    assert path, "no route found"
    assert_path_invariants(path, s.grid, s.start, s.goal, s.diag)
    assert len(path) == s.tiles, f"not a shortest route: {len(path)} tiles, a shortest one has {s.tiles}"


def _check(s: Scenario) -> None:
    path, expanded = _search(s)
    _check_route(path, s)
    again = [astar(s.start, s.goal, s.grid, diag=s.diag) for _ in range(2)]
    assert again == [path, path], "the same search gave another route"
    walkable = s.grid.width * s.grid.height - len(s.grid.blocked)
    assert expanded <= walkable, f"a tile was expanded more than once: {expanded} expansions, {walkable} walkable tiles"
    assert expanded <= s.expanded, (
        f"the search does more work than its budget: {expanded} tiles expanded, {s.expanded} allowed "
        "(lower the budget when the search improves; raise it only for a change that is meant to cost this)")


def test_astar_perf_open_grid_50x50() -> None:
    _check(SCENARIOS["open"])


def test_astar_perf_maze_50x50() -> None:
    _check(SCENARIOS["maze"])


def test_astar_perf_diagonal_50x50() -> None:
    _check(SCENARIOS["diagonal"])


def test_astar_perf_worst_case_spiral() -> None:
    _check(SCENARIOS["spiral"])


@pytest.mark.fast
def test_astar_perf_straight_across_open_ground() -> None:
    _check(SCENARIOS["straight"])


def test_astar_determinism_across_runs() -> None:
    """Ensure same inputs always produce same path."""
    blocked = {5 * 20 + 5, 5 * 20 + 6, 6 * 20 + 5, 10 * 20 + 10, 10 * 20 + 11, 11 * 20 + 10}
    grid = _grid(20, blocked)
    paths = [astar((0, 0), (19, 19), grid, diag=False) for _ in range(5)]
    assert paths[0] and all(path == paths[0] for path in paths)


@pytest.mark.fast
@pytest.mark.parametrize("name", [name for name, s in SCENARIOS.items() if not s.diag])
def test_the_pinned_route_lengths_are_shortest_ones(name: str) -> None:
    """A breadth-first flood (an oracle for ``Scenario.tiles``; nothing here is timed or counted as the search's)."""
    s = SCENARIOS[name]
    seen, frontier, tiles = {s.start}, [s.start], 1
    while frontier and s.goal not in seen:
        reached = []
        for x, y in frontier:
            for tile in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if tile not in seen and s.grid.is_walkable(tile):
                    seen.add(tile)
                    reached.append(tile)
        frontier, tiles = reached, tiles + 1
    assert s.goal in seen and tiles == s.tiles


def _probe_costs(names: tuple[str, ...] = tuple(SCENARIOS), rounds: int = 7) -> dict[str, float]:
    """Each scenario's time per neighbour probe, in millionths of one calibration loop (and that loop's ``loop_ms``).

    Medians, of ``rounds`` samples a scenario and of the calibration read every third round, in turn: one stalled
    sample moves neither, and a runner that is slow or busy throughout slows both."""
    chosen = {name: SCENARIOS[name] for name in names}
    probes = {}
    for name, s in chosen.items():
        probes[name] = _search(s)[1] * (8 if s.diag else 4)
        astar(s.start, s.goal, s.grid, diag=s.diag)  # (once untimed: the interpreter warm)
    loops: list[float] = []
    samples: dict[str, list[float]] = {name: [] for name in chosen}
    for turn in range(rounds):
        if turn % 3 == 0:
            loops.append(cpu_ms())
        for name, s in chosen.items():
            began = time.perf_counter()
            for _ in range(s.repeat):
                astar(s.start, s.goal, s.grid, diag=s.diag)
            samples[name].append((time.perf_counter() - began) * 1000 / s.repeat)
    loop_ms = statistics.median(loops)
    costs = {name: statistics.median(samples[name]) / probes[name] / loop_ms * 1e6 for name in chosen}
    return {**costs, "loop_ms": loop_ms}


def _check_runtime(costs: dict[str, float]) -> None:
    over = {name: round(cost, 1) for name, cost in costs.items() if name != "loop_ms" and cost > MAX_PROBE_COST}
    assert not over, (
        f"the search costs more per neighbour probe than {MAX_PROBE_COST:g} millionths of the calibration loop: {over} "
        f"(all: { {k: round(v, 1) for k, v in costs.items()} })")


@pytest.mark.integration
def test_astar_runtime_per_probe_against_the_calibration_loop(record_property: Any) -> None:
    costs = _probe_costs()
    for name, cost in costs.items():
        record_property(f"astar_probe_cost_{name}", round(cost, 2))
    _check_runtime(costs)


# --- The guards trip when the search is broken (faults injected for the test only) ---

_ASTAR = importlib.import_module("engine.pathfinding.astar")  # (the module: the package's ``astar`` is the function)


def _broken_routes() -> dict[str, list[Tile]]:
    s = SCENARIOS["maze"]
    good = astar(s.start, s.goal, s.grid, diag=False)
    wall = next(i for i, (x, _y) in enumerate(good) if x == 4)  # (where the route goes through the first wall's gap)
    gap_x, gap_y = good[wall]
    return {
        "none": [],
        "through a wall": [*good[:wall], (gap_x, gap_y + 1), *good[wall + 1:]],
        "a jump": [*good[:10], *good[12:]],
        "stops short": good[:-1],
        "starts elsewhere": good[1:],
        "a detour": [*good[:1], *good[:1], *good[1:]],
    }


@pytest.mark.fast
@pytest.mark.parametrize("fault", ["none", "through a wall", "a jump", "stops short", "starts elsewhere", "a detour"])
def test_a_broken_route_fails_the_route_check(fault: str) -> None:
    with pytest.raises(AssertionError):
        _check_route(_broken_routes()[fault], SCENARIOS["maze"])


@pytest.mark.fast
def test_a_search_that_takes_the_newest_tile_first_fails_the_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """The open list as a stack (depth first): still a legal route, no longer a shortest one."""
    monkeypatch.setattr(_ASTAR, "heapq", types.SimpleNamespace(heappush=lambda heap, entry: heap.append(entry),
                                                               heappop=lambda heap: heap.pop()))
    with pytest.raises(AssertionError, match="not a shortest route"):
        _check(SCENARIOS["open"])


@pytest.mark.fast
@pytest.mark.parametrize("name", ["diagonal", "straight"])
def test_a_search_without_its_heuristic_is_over_its_work_budget(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """No heuristic (Dijkstra's flood): the same shortest route, found by expanding the whole grid."""
    monkeypatch.setattr(_ASTAR, "_heuristic", lambda a, b, *, diag: 0)
    path, expanded = _search(SCENARIOS[name])
    _check_route(path, SCENARIOS[name])  # (still a correct route: only the work gives it away)
    assert expanded > 20 * SCENARIOS[name].expanded
    with pytest.raises(AssertionError, match="more work than its budget"):
        _check(SCENARIOS[name])


@pytest.mark.fast
@pytest.mark.parametrize("name", list(SCENARIOS))
def test_a_search_that_expands_tiles_twice_fails_the_check(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """Every open-list entry queued twice: each tile is expanded again from its duplicate."""
    import heapq

    def push_twice(heap: list, entry: tuple) -> None:
        heapq.heappush(heap, entry)
        heapq.heappush(heap, entry)

    monkeypatch.setattr(_ASTAR, "heapq", types.SimpleNamespace(heappush=push_twice, heappop=heapq.heappop))
    with pytest.raises(AssertionError, match="expanded more than once|more work than its budget"):
        _check(SCENARIOS[name])


@pytest.mark.integration
def test_a_search_slowed_several_times_over_fails_the_runtime_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fixed extra work in the production module's heuristic (no sleep): the same routes and the same work count,
    several times the time. The count can't see it; the runtime check must."""
    heuristic = _ASTAR._heuristic

    def slow(a: Tile, b: Tile, *, diag: bool) -> int:
        sum(range(1500))
        return heuristic(a, b, diag=diag)

    names = ("straight",)
    before = {name: _search(SCENARIOS[name]) for name in names}
    monkeypatch.setattr(_ASTAR, "_heuristic", slow)
    assert {name: _search(SCENARIOS[name]) for name in names} == before
    with pytest.raises(AssertionError, match="costs more per neighbour probe"):
        _check_runtime(_probe_costs(names))


@pytest.mark.integration
def test_one_stalled_sample_does_not_fail_the_runtime_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """The failure this file had: one timed search held up for 0.55 s (a full garbage collection late in a long
    suite, a descheduled runner) while the search itself was as fast as ever. One sample of seven: the medians don't
    move."""
    search, calls = astar, []

    def stalled_once(*args: Any, **kwargs: Any) -> list[Tile]:
        calls.append(time.perf_counter())
        if len(calls) == 5:  # (the third timed sample: the count and the warm-up come first)
            time.sleep(0.55)
        return search(*args, **kwargs)

    monkeypatch.setitem(globals(), "astar", stalled_once)
    costs = _probe_costs(("maze",))
    assert len(calls) == 9 and max(b - a for a, b in zip(calls, calls[1:])) > 0.5, "the stall happened in a sample"
    _check_runtime(costs)
