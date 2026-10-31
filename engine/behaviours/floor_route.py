"""FloorRoute: an HD-2D character walks a route of points on different floors, finding its way over stairs and
bridges (Milestone 16 Stage 3).

Each leg is planned on the scene's navigation grid (``engine.hd2d.world.World.path``) and walked with the same
height-aware movement as the player, so it climbs only where floors connect and never walks through a wall. In a
2D scene (no HD-2D floors) it does nothing.
"""

from __future__ import annotations

import math
from typing import Any

from engine.hd2d.world import World as Hd2dWorld
from engine.hd2d.world import elevation_of

from .base import Behaviour, ParamDef
from .registry import register_behaviour

PX = 32.0  # px per metre (engine.hd2d.settings.PIXELS_PER_METRE)


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
        if not self.path:
            goal = self.route[self.index]
            self.path = world.path((fx / PX, fy / PX, elevation_of(sprite)), (goal[0] / PX, goal[1] / PX, goal[2] / PX))
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

    def _arrive(self) -> None:
        self.path = []
        self.index = (self.index + 1) % len(self.route)
        self._waiting = self.wait
