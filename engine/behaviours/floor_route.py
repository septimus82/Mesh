"""FloorRoute: an HD-2D character walks a route of points on different floors, finding its way over stairs and
bridges (Milestone 16 Stage 3).

Each leg is planned on the scene's navigation grid (``engine.hd2d.world.World.path``) and walked with the same
height-aware movement as the player, so it climbs only where floors connect and never walks through a wall. In a
2D scene (no HD-2D floors) it does nothing.

Put somewhere it can't stand (deep or blocking water: a start point there, a river carved under it, a teleport;
#461 R4B), it first walks out: towards the nearest places it could stand (``World.ways_out``, nearest first, the
same each time), with the same movement, which never takes it deeper. A way out it makes no headway towards for
STUCK_S is given up for the next; with none left it stays where it is, stranded: said once in the log and as a
``stranded`` gameplay event (``mesh_hd2d_stranded`` on the character), until it can stand again (moved by an event).
"""

from __future__ import annotations

import logging
import math
from typing import Any

from engine.hd2d.world import NAV_HALF, elevation_of
from engine.hd2d.world import World as Hd2dWorld

from .base import Behaviour, ParamDef
from .registry import register_behaviour

PX = 32.0  # px per metre (engine.hd2d.settings.PIXELS_PER_METRE)
STUCK_S = 1.0  # s: no headway towards a way out for this long: the next one
logger = logging.getLogger(__name__)


@register_behaviour(
    "FloorRoute",
    description="HD-2D: walks between points on different floors, using stairs and bridges.",
    config_fields=[
        {"name": "route", "description": "Points to visit in turn: [x, y, elevation] in px", "type": "array",
         "default": []},
        {"name": "speed", "description": "Walking speed (px per second)", "type": "float", "default": 60.0},
        {"name": "wait", "description": "Seconds to stand at each point", "type": "float", "default": 1.0},
    ],
)
class FloorRouteBehaviour(Behaviour):
    PARAM_DEFS = {
        "route": ParamDef(list, default=[], description="Points to visit in turn: [x, y, elevation] in px"),
        "speed": ParamDef(float, default=60.0, description="Walking speed (px per second)"),
        "wait": ParamDef(float, default=1.0, description="Seconds to stand at each point"),
    }

    def __init__(self, entity: Any, window: Any, **config: Any) -> None:
        super().__init__(entity, window, **config)
        self.route: list[tuple[float, float, float]] = []
        for point in self.config.get("route") or []:
            if isinstance(point, (list, tuple)) and len(point) in (2, 3):
                try:
                    self.route.append((float(point[0]), float(point[1]), float(point[2]) if len(point) == 3 else 0.0))
                except (TypeError, ValueError):
                    continue
        self.speed = float(self.config.get("speed", 60.0) or 60.0)
        self.wait = float(self.config.get("wait", 1.0) or 0.0)
        self.index = 0
        self.path: list[tuple[float, float, float]] = []  # this leg's waypoints (metres)
        self._waiting = 0.0
        self._stuck = 0.0
        self._ways: list[tuple[float, float, float]] | None = None  # out of deep water: where to, nearest first
        self._best = math.inf  # the nearest it has come to the way out it is making for (m)

    def _feet(self) -> tuple[float, float]:
        from engine.physics_runtime import _sprite_to_aabb  # noqa: PLC0415

        box = _sprite_to_aabb(self.entity)
        return box.x, box.y

    def update(self, dt: float) -> None:
        world = getattr(self.window, "hd2d_world", None)
        sprite: Any = self.entity
        sprite.mesh_velocity_x = sprite.mesh_velocity_y = 0.0
        if not isinstance(world, Hd2dWorld) or not self.route:
            return
        if self._waiting > 0.0:
            self._waiting -= dt
            return
        fx, fy = self._feet()
        z = elevation_of(sprite)
        if self._ways is not None or getattr(sprite, "mesh_hd2d_stranded", None):
            if world.stand(fx / PX, fy / PX, z, *NAV_HALF) is None:
                self._walk_out(world, fx, fy, z, dt)
                return
            self._ways, sprite.mesh_hd2d_stranded = None, None  # out: on with its route
        if not self.path:
            goal = self.route[self.index]
            self.path = world.path((fx / PX, fy / PX, z), (goal[0] / PX, goal[1] / PX, goal[2] / PX))
            if not self.path and world.stand(fx / PX, fy / PX, z, *NAV_HALF) is None:
                self._ways, self._best, self._stuck = world.ways_out(fx / PX, fy / PX, z), math.inf, 0.0
                self._walk_out(world, fx, fy, z, dt)  # (it can't stand here: deep or blocking water)
                return
            if not self.path:  # unreachable from here: try the next point after a pause
                self._arrive()
                return
        tx, ty = self.path[0][0] * PX, self.path[0][1] * PX
        dist = math.hypot(tx - fx, ty - fy)
        if dist <= 1.0:
            self.path.pop(0)
            if not self.path:
                self._arrive()
            return
        step = min(self.speed * dt, dist)
        scene = getattr(self.window, "scene_controller", None)
        world.move(sprite, ((tx - fx) / dist * step, (ty - fy) / dist * step), getattr(scene, "solid_sprites", None))
        nx, ny = self._feet()
        moved = math.hypot(nx - fx, ny - fy)
        if dt > 0:
            sprite.mesh_velocity_x, sprite.mesh_velocity_y = (nx - fx) / dt, (ny - fy) / dt
        self._stuck = self._stuck + dt if moved < step * 0.25 else 0.0
        if self._stuck > 0.75:  # blocked (someone in the way): plan again
            self.path, self._stuck = [], 0.0

    def _walk_out(self, world: Hd2dWorld, fx: float, fy: float, z: float, dt: float) -> None:
        """A step towards the nearest way out of the water it can't stand in; stranded when none is left."""
        sprite: Any = self.entity
        if not self._ways:
            if not getattr(sprite, "mesh_hd2d_stranded", None):
                where = f"({fx:.0f}, {fy:.0f}) px"
                sprite.mesh_hd2d_stranded = f"can't walk out of the water at {where}"
                logger.warning("[Mesh][HD-2D] %s is stranded: it can't walk out of the water at %s",
                               getattr(sprite, "mesh_name", "") or "a character", where)
                from engine.event_emit import emit_gameplay_event  # noqa: PLC0415

                emit_gameplay_event(self.window, "stranded", {"who": str(getattr(sprite, "mesh_name", "") or ""),
                                                              "x": round(fx, 1), "y": round(fy, 1)},
                                    source_entity_id=None, source_behaviour="FloorRoute")
            self._ways = None
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
        scene = getattr(self.window, "scene_controller", None)
        world.move(sprite, ((tx * PX - fx) / dist * step, (ty * PX - fy) / dist * step),
                   getattr(scene, "solid_sprites", None))

    def _arrive(self) -> None:
        self.path = []
        self.index = (self.index + 1) % len(self.route)
        self._waiting = self.wait
