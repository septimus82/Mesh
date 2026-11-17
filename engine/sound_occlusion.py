"""Whether a wall stands between a listener and a sound (Milestone 21C1): the question, on the room's own collision
geometry. ``engine.sound_emitters`` asks it for the emitters whose ``occlusion`` is on, and turns them down.

**A 2D room:** its wall tiles (the tile map's collision layer, as the navigation grid has them:
``scene_controller.get_nav_grid``). A sound is behind a wall when a wall tile lies on the straight line of tiles
from the listener's tile to the sound's (``engine.pathfinding.los.raycast_tiles``), or the line squeezes diagonally
between two. Neither end's own tile counts: a machine set in a wall is heard from in front of it. Solid objects (a
crate, a person) are not walls.

**An HD-2D room:** the wall colliders of its structures (``engine.hd2d.world.World.walls``: a model's ``wall``
nodes, and blocking scatter's) that a person can't see over and that aren't a post: at least ``MIN_HEIGHT`` m tall
and ``MIN_SPAN`` m long. The line is drawn in 3D, from the listener's ears (``EAR`` m over their feet) to the
sound's own height, so a sound up on a plateau is heard over a wall below it, and through a doorway's gap under
its lintel. A wall either end stands inside doesn't count. Not walls: floors, platforms and their raised ground,
sculpted hills, water, fences and railings, furniture, lamp posts, and anything only drawn (a roof: it has no
collider, cut away or not).

One answer, yes or no, per line: nothing is measured of how thick the wall is or how far round it the sound goes.
"""

from __future__ import annotations

from typing import Any

EAR = 1.2  # m: a listener's ears over their feet
MIN_HEIGHT = 1.5  # m: a wall this tall or taller stands in a sound's way (engine.hd2d.world.BODY: a person's height)
MIN_SPAN = 1.0  # m: and this long or longer (a lamp post, an awning's post: not walls)
PX_PER_M = 32.0

Point = tuple[float, float, float]  # px east, px north, px up


def blockers(window: Any) -> tuple[Any, ...] | None:
    """What can stand in a sound's way in the room now, or None (nothing can). Compared with ``same`` to know the
    room's walls changed (another room, a reload, scatter repainted): its parts are the objects themselves."""
    world = getattr(window, "hd2d_world", None)
    if world is not None:
        return ("3d", world, world.walls)
    controller = getattr(window, "scene_controller", None)
    get = getattr(controller, "get_nav_grid", None)
    grid = get() if callable(get) else None
    if grid is None or not getattr(grid, "blocked", None):
        return None
    return ("2d", grid)


def same(a: tuple[Any, ...] | None, b: tuple[Any, ...] | None) -> bool:
    if a is None or b is None:
        return a is b
    return len(a) == len(b) and all(x is y for x, y in zip(a, b))


def acoustic_walls(what: tuple[Any, ...] | None) -> list[Any]:
    """Of an HD-2D room's wall colliders, the ones a sound doesn't pass (found once per ``blockers``)."""
    if what is None or what[0] != "3d":
        return []
    out = []
    for wall in what[2]:
        span = (2.0 * max(wall.turned[2], wall.turned[3]) if wall.turned is not None
                else max(wall.hi[0] - wall.lo[0], wall.hi[1] - wall.lo[1]))
        if wall.hi[2] - wall.lo[2] >= MIN_HEIGHT and span >= MIN_SPAN:
            out.append(wall)
    return out


def blocked(what: tuple[Any, ...] | None, walls: list[Any], listener: Point, source: Point) -> bool:
    """Whether a wall stands between the listener (their feet) and the sound. ``walls``: ``acoustic_walls(what)``."""
    if what is None:
        return False
    if what[0] == "2d":
        return _tiles_between(what[1], listener, source)
    a = (listener[0] / PX_PER_M, listener[1] / PX_PER_M, listener[2] / PX_PER_M + EAR)
    b = (source[0] / PX_PER_M, source[1] / PX_PER_M, source[2] / PX_PER_M)
    x0, x1 = (a[0], b[0]) if a[0] <= b[0] else (b[0], a[0])
    y0, y1 = (a[1], b[1]) if a[1] <= b[1] else (b[1], a[1])
    for wall in walls:
        if wall.lo[0] > x1 or wall.hi[0] < x0 or wall.lo[1] > y1 or wall.hi[1] < y0:
            continue  # (its box is nowhere near the line: most walls, most of the time)
        if _crosses(wall, a, b):
            return True
    return False


def _crosses(wall: Any, a: Point, b: Point) -> bool:
    """Whether the line from ``a`` to ``b`` (m) passes through the wall's box (in its own turned frame, if it is
    turned), neither end inside it."""
    lo, hi = wall.lo, wall.hi
    if wall.turned is not None:
        cx, cy, ex, ey, c, s = wall.turned
        a = ((a[0] - cx) * c + (a[1] - cy) * s, -(a[0] - cx) * s + (a[1] - cy) * c, a[2])
        b = ((b[0] - cx) * c + (b[1] - cy) * s, -(b[0] - cx) * s + (b[1] - cy) * c, b[2])
        lo, hi = (-ex, -ey, lo[2]), (ex, ey, hi[2])
    for p in (a, b):
        if lo[0] <= p[0] <= hi[0] and lo[1] <= p[1] <= hi[1] and lo[2] <= p[2] <= hi[2]:
            return False  # (it stands in the wall: a machine set into it, a listener pressed against it)
    enter, leave = 0.0, 1.0
    for i in range(3):
        d = b[i] - a[i]
        if abs(d) < 1e-9:
            if not lo[i] < a[i] < hi[i]:
                return False
            continue
        t0, t1 = (lo[i] - a[i]) / d, (hi[i] - a[i]) / d
        if t0 > t1:
            t0, t1 = t1, t0
        enter, leave = max(enter, t0), min(leave, t1)
        if enter >= leave:
            return False
    return True


def _tiles_between(grid: Any, listener: Point, source: Point) -> bool:
    from engine.pathfinding.los import raycast_tiles  # noqa: PLC0415

    def wall(tile: tuple[int, int]) -> bool:
        return bool(grid.in_bounds(tile)) and not grid.is_walkable(tile)

    start = grid.world_to_tile(listener[0], listener[1])
    goal = grid.world_to_tile(source[0], source[1])
    before = start
    for tile in raycast_tiles(start, goal)[1:]:
        if tile != goal and wall(tile):
            return True
        if tile[0] != before[0] and tile[1] != before[1] and wall((tile[0], before[1])) and wall((before[0], tile[1])):
            return True  # (a diagonal step between two wall tiles that meet at their corners: a wall's corner)
        before = tile
    return False
