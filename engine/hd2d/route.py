"""FloorRoute's decision logic, graphics-free (HD-2D online M4-4, owner decision OD7): a character walks a route of
points on different floors, finding its way over stairs and bridges. One model, two runtimes: single-player's
``FloorRoute`` behaviour (engine.behaviours.floor_route) is a thin adapter over it, and the net authority
(mesh_net.scene_room) runs it for its enemies, both through the one floor solver (``World.path``, ``World.move``).

Each leg is planned on the scene's navigation grid (``World.path``) and walked with the same height-aware movement as
the player, so it climbs only where floors connect and never walks through a wall. Without a World (a 2D scene) it
does nothing.

Put somewhere it can't stand (deep or blocking water: a start point there, a river carved under it, a teleport;
#461 R4B), it first walks out: towards the nearest places it could stand (``World.ways_out``, nearest first, the
same each time), with the same movement, which never takes it deeper. A way out it makes no headway towards for
STUCK_S is given up for the next; with none left it stays where it is, stranded (``mesh_hd2d_stranded`` on the body,
and ``on_strand`` once), looking again every RETRY_S, until it can stand (judged by its own feet box, as it is moved).
Planning a leg again and again without headway (REPLANS in a row) gives that point up for BACK_OFF_S (``on_stuck``,
once).

The body is anything ``World.move`` moves (a game sprite, or the authority's ``Body``): ``center_x``/``center_y``, its
size, ``mesh_entity_data`` (its elevation) and its collider. Its feet box is ``engine.physics_model.entity_aabb``.
Each update also sets its ``mesh_velocity_x``/``_y`` (px/s: what an Animator walks or stands by).

Imports only engine.hd2d.world, engine.physics_model and the standard library: no Arcade, no window.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Iterable

from engine.hd2d.world import NAV_HALF, World, elevation_of
from engine.physics_model import entity_aabb

PX = 32.0  # px per metre (engine.hd2d.settings.PIXELS_PER_METRE)
SPEED = 60.0  # px/s: the behaviour's default speed
WAIT = 1.0  # s: its default wait at each point
STUCK_S = 1.0  # s: no headway towards a way out for this long: the next one
RETRY_S = 5.0  # s: stranded, it looks for a way out again this often (the ground may have changed)
REPLANS = 3  # routes planned again in a row without reaching a point: it gives that point up for a while
BACK_OFF_S = 5.0  # s: ... this long before the next

Sweep = Callable[[Any, tuple[float, float], list[Any]], Any]


def parse_route(points: Any) -> list[tuple[float, float, float]]:
    """A route as authored (``[x, y]`` or ``[x, y, elevation]`` px each); anything else left out."""
    route: list[tuple[float, float, float]] = []
    for point in points or []:
        if isinstance(point, (list, tuple)) and len(point) in (2, 3):
            try:
                route.append((float(point[0]), float(point[1]), float(point[2]) if len(point) == 3 else 0.0))
            except (TypeError, ValueError):
                continue
    return route


class FloorRoute:
    """One character's walk along its route. ``on_stuck(body, point)``: it gave up on reaching ``point`` for a while
    (said once); ``on_strand(body, where, fx, fy)``: it is stranded where its feet are (fx, fy px), first time."""

    def __init__(self, route: list[tuple[float, float, float]], speed: float = SPEED, wait: float = WAIT,
                 on_stuck: Callable[[Any, tuple[float, float]], None] | None = None,
                 on_strand: Callable[[Any, str, float, float], None] | None = None) -> None:
        self.route = route
        self.speed = speed
        self.wait = wait
        self.on_stuck, self.on_strand = on_stuck, on_strand
        self.index = 0
        self.path: list[tuple[float, float, float]] = []  # this leg's waypoints (metres)
        self._waiting = 0.0
        self._stuck = 0.0
        self._ways: list[tuple[float, float, float]] | None = None  # out of deep water: where to, nearest first
        self._best = math.inf  # the nearest it has come to the way out it is making for (m)
        self._retry = 0.0  # stranded: until it looks for a way out again (s)
        self._low = math.inf  # the least far into blocking water it has come, walking out (``World.blocked``)
        self._replans = 0  # routes planned again in a row without reaching a point
        self._said_stuck = False  # (said once)

    @classmethod
    def from_config(cls, config: dict[str, Any], **hooks: Any) -> FloorRoute:
        """From the behaviour's settings (``route``, ``speed``, ``wait``), as the behaviour reads them."""
        return cls(parse_route(config.get("route")), float(config.get("speed", SPEED) or SPEED),
                   float(config.get("wait", WAIT) or 0.0), **hooks)

    @staticmethod
    def _feet(body: Any) -> tuple[float, float]:
        box = entity_aabb(body)
        return box.x, box.y

    @staticmethod
    def _half(body: Any) -> tuple[float, float]:
        """Its feet box's half size (m), as the world moves it (at least the navigation grid's)."""
        box = entity_aabb(body)
        return max(NAV_HALF[0], box.w / 2 / PX), max(NAV_HALF[1], box.h / 2 / PX)

    def update(self, world: World | None, body: Any, dt: float, solids: Iterable[Any] | None = None,
               sweep: Sweep | None = None) -> None:
        """One update of ``dt`` s: ``body`` walks on through ``world`` (None: a 2D scene, nothing happens), blocked by
        ``solids`` on its level, with ``sweep`` the 2D move (World.move's; None: the game's)."""
        sprite: Any = body
        sprite.mesh_velocity_x = sprite.mesh_velocity_y = 0.0
        if not isinstance(world, World) or not self.route:
            return
        if self._waiting > 0.0:
            self._waiting -= dt
            return
        fx, fy = self._feet(body)
        z = elevation_of(sprite)
        half = self._half(body)  # (its own feet: what it is moved by)
        if self._ways is not None or getattr(sprite, "mesh_hd2d_stranded", None):
            if world.stand(fx / PX, fy / PX, z, *half) is None:
                if self._ways is None:  # stranded: now and then it looks again
                    self._retry -= dt
                    if self._retry > 0.0:
                        return
                    self._ways, self._best, self._stuck = world.ways_out(fx / PX, fy / PX, z), math.inf, 0.0
                self._walk_out(world, body, fx, fy, z, dt, solids, sweep)
                return
            self._ways, sprite.mesh_hd2d_stranded, self._low = None, None, math.inf  # out: on with its route
        if not self.path:
            goal = self.route[self.index]
            self.path = world.path((fx / PX, fy / PX, z), (goal[0] / PX, goal[1] / PX, goal[2] / PX))
            if not self.path and world.stand(fx / PX, fy / PX, z, *half) is None:
                self._ways, self._best, self._stuck = world.ways_out(fx / PX, fy / PX, z), math.inf, 0.0
                self._walk_out(world, body, fx, fy, z, dt, solids, sweep)  # (it can't stand here: deep or blocking
                return  # water)
            if not self.path:  # unreachable from here: try the next point after a pause (a second at least: never
                self._arrive()  # planning every frame)
                self._waiting = max(self._waiting, 1.0)
                return
        tx, ty = self.path[0][0] * PX, self.path[0][1] * PX
        dist = math.hypot(tx - fx, ty - fy)
        if dist <= 1.0:
            self.path.pop(0)
            self._replans = 0
            if not self.path:
                self._arrive()
            return
        step = min(self.speed * dt, dist)
        world.move(sprite, ((tx - fx) / dist * step, (ty - fy) / dist * step), solids, sweep=sweep)
        nx, ny = self._feet(body)
        moved = math.hypot(nx - fx, ny - fy)
        if dt > 0:
            sprite.mesh_velocity_x, sprite.mesh_velocity_y = (nx - fx) / dt, (ny - fy) / dt
        self._stuck = self._stuck + dt if moved < step * 0.25 else 0.0
        if self._stuck > 0.75:  # blocked (someone in the way): plan again
            self.path, self._stuck = [], 0.0
            self._replans += 1
            if self._replans >= REPLANS:  # (no headway however often it plans: that point, later; said once)
                if not self._said_stuck:
                    self._said_stuck = True
                    if self.on_stuck is not None:
                        self.on_stuck(body, self.route[self.index][:2])
                self._replans = 0
                self._arrive()
                self._waiting = max(self._waiting, BACK_OFF_S)

    def _walk_out(self, world: World, body: Any, fx: float, fy: float, z: float, dt: float,
                  solids: Iterable[Any] | None, sweep: Sweep | None) -> None:
        """A step out of the water it can't stand in: in blocking water down its steepest fall, else towards the
        nearest way out (``World.ways_out``) still left; stranded when none is (or it makes no headway out)."""
        sprite: Any = body
        held = world.blocked(fx / PX, fy / PX, z)
        if held > 0.0:
            # (in blocking water: whichever way its ways out lie (if any are near), down the water's steepest fall,
            # the quickest way out of it, as the world lets it go (of sixteen ways, the steepest first). Headway
            # only while that takes it further out than it has yet been, by a twentieth of each step at least: never
            # back and forth over its edge, and stranded if that stops for STUCK_S)
            r = self.speed * dt / PX
            before = (sprite.center_x, sprite.center_y)
            falls = sorted((world.blocked(fx / PX + math.cos(i * math.tau / 16) * r,
                                          fy / PX + math.sin(i * math.tau / 16) * r, z), i) for i in range(16))
            headway = False
            for fall, i in falls:
                if fall >= held:
                    break
                a = i * math.tau / 16
                world.move(sprite, (math.cos(a) * self.speed * dt, math.sin(a) * self.speed * dt), solids, sweep=sweep)
                if (sprite.center_x, sprite.center_y) != before:
                    nx, ny = self._feet(body)
                    after = world.blocked(nx / PX, ny / PX, z)
                    if after < min(held, self._low) - 0.05 * r:
                        self._low, headway = after, True
                    break
            self._stuck = 0.0 if headway else self._stuck + dt
            if self._stuck > STUCK_S:
                self._strand(body, fx, fy)
            return
        if self._low <= -1e8:  # (just walked out of blocking water down its fall: where it might stand now is
            self._low = -math.inf  # looked for again from here, once, not from where it started)
            self._ways, self._best, self._stuck = world.ways_out(fx / PX, fy / PX, z), math.inf, 0.0
        if not self._ways:
            self._strand(body, fx, fy)
            return
        tx, ty, _tz = self._ways[0]
        dist = math.hypot(tx * PX - fx, ty * PX - fy)
        if dist + 0.5 < self._best:
            self._best, self._stuck = dist, 0.0
        else:
            self._stuck += dt
        if self._stuck > STUCK_S or dist <= 1.0:  # (no headway: the next way out; reached: try standing again)
            self._ways.pop(0)
            self._best, self._stuck = math.inf, 0.0
            return
        step = min(self.speed * dt, dist)
        world.move(sprite, ((tx * PX - fx) / dist * step, (ty * PX - fy) / dist * step), solids, sweep=sweep)

    def _strand(self, body: Any, fx: float, fy: float) -> None:
        """No way out: it stays put (``mesh_hd2d_stranded``; ``on_strand`` the first time), and looks again after
        RETRY_S."""
        sprite: Any = body
        if not getattr(sprite, "mesh_hd2d_stranded", None):
            where = f"({fx:.0f}, {fy:.0f}) px"
            sprite.mesh_hd2d_stranded = f"can't walk out of the water at {where}"
            if self.on_strand is not None:
                self.on_strand(body, where, fx, fy)
        self._ways, self._retry, self._stuck = None, RETRY_S, 0.0

    def _arrive(self) -> None:
        self.path = []
        self.index = (self.index + 1) % len(self.route)
        self._waiting = self.wait
