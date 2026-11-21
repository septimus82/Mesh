"""Can a character walk this route? Problems in words, for the route editor.

Uses the room's own navigation grid (``engine.pathfinding``: the wall layer, plus solid objects) and the
existing line-of-sight and A* routines; nothing is reimplemented. "Walk between points" walks straight
from point to point, so a leg is only walkable if its straight line is clear: a route can be inside the
map and still not walkable, and is reported as such.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engine.pathfinding.astar import astar
from engine.pathfinding.los import line_of_sight_clear
from engine.pathfinding.nav_grid import NavGrid, build_nav_grid_from_scene_payload


@dataclass(frozen=True)
class Problem:
    kind: str  # "outside" | "wall" | "blocked"
    text: str
    point: int | None = None  # 0-based index of the point it is about
    leg: tuple[int | None, int] | None = None  # (from, to) point indexes; from None = where the character starts


def _grid(scene: dict[str, Any]) -> NavGrid | None:
    """The room's grid with solid objects added. Tiles are (column, row from the top), as the grid stores them."""
    grid = build_nav_grid_from_scene_payload(scene)
    if grid is None:
        return None
    blocked = set(grid.blocked)
    for entity in scene.get("entities") or []:
        if isinstance(entity, dict) and entity.get("solid") and entity.get("tag") != "player":
            tile = _tile(grid, float(entity.get("x", 0)), float(entity.get("y", 0)))
            if grid.in_bounds(tile):
                blocked.add(grid.to_index(tile))
    return NavGrid(grid.width, grid.height, grid.tile_w, grid.tile_h, frozenset(blocked))


def _tile(grid: NavGrid, x: float, y: float) -> tuple[int, int]:
    """World point (y up) -> (column, row from the top)."""
    return int(x // grid.tile_w), grid.height - 1 - int(y // grid.tile_h)


def route_problems(scene: dict[str, Any], start: tuple[float, float] | None, points: list[tuple[float, float]],
                   *, loop: bool = True, ignore: str | None = None) -> list[Problem]:
    """What would stop a character walking ``points`` in order (back to the first if ``loop``), starting at
    ``start``. ``ignore``: the walker's own id (it doesn't block itself)."""
    if ignore:
        scene = {**scene, "entities": [e for e in scene.get("entities") or [] if not (isinstance(e, dict) and e.get("id") == ignore)]}
    grid = _grid(scene)
    out: list[Problem] = []
    if grid is None:
        return out
    tiles = [_tile(grid, x, y) for x, y in points]
    bad: set[int] = set()
    for i, tile in enumerate(tiles):
        if not grid.in_bounds(tile):
            out.append(Problem("outside", f"Point {i + 1} is outside the map.", point=i))
            bad.add(i)
        elif not grid.is_walkable(tile):
            out.append(Problem("wall", f"Point {i + 1} is inside a wall or a solid object: nobody can stand there.", point=i))
            bad.add(i)
    legs: list[tuple[int | None, int]] = []
    if start is not None and tiles:
        legs.append((None, 0))
    legs += [(i, i + 1) for i in range(len(tiles) - 1)]
    if loop and len(tiles) > 2:
        legs.append((len(tiles) - 1, 0))
    for a, b in legs:
        if b in bad or (a is not None and a in bad):
            continue
        from_tile = _tile(grid, *start) if a is None and start is not None else tiles[a or 0]
        if not grid.in_bounds(from_tile) or line_of_sight_clear(from_tile, tiles[b], grid):
            continue
        where = "where it starts" if a is None else f"point {a + 1}"
        around = " There is a way round: add a point at the corner." if astar(from_tile, tiles[b], grid) else ""
        out.append(Problem("blocked", f"A wall is in the way from {where} to point {b + 1}: it walks straight from point "
                                      f"to point, so it would stop there.{around}", leg=(a, b)))
    return out
