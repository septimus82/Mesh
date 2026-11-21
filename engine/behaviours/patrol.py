"""Sprite patrol behaviour."""

from __future__ import annotations

import math
from typing import List, Tuple

from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "Patrol",
    description="Moves between waypoints defined in the scene data.",
    config_fields=[
        {
            "name": "patrol_points",
            "description": "List of {x,y} waypoints to visit",
            "type": "array",
            "default": [],
        },
        {
            "name": "patrol_speed",
            "description": "Movement speed between points",
            "type": "float",
            "default": 80.0,
        },
        {
            "name": "points",
            "description": "Alias for patrol_points",
            "type": "array",
            "default": [],
        },
        {
            "name": "speed",
            "description": "Alias for patrol_speed",
            "type": "float",
            "default": 80.0,
        },
    ],
)
class PatrolBehaviour(Behaviour):
    """Moves a sprite between predefined patrol points."""

    PARAM_DEFS = {
        "patrol_points": ParamDef(list, default=[], description="List of {x,y} waypoints to visit"),
        "patrol_speed": ParamDef(float, default=80.0, description="Movement speed between points"),
    }

    def __init__(self, entity, window, **config) -> None:
        super().__init__(entity, window, **config)
        raw_points = self.config.get("patrol_points") or []
        self.points: List[Tuple[float, float]] = []
        for point in raw_points:
            try:
                self.points.append((float(point["x"]), float(point["y"])))
            except (KeyError, TypeError, ValueError):
                continue

        self.speed = float(self.config.get("patrol_speed", 80.0))
        self.current_index: int = 0
        self._disabled = False

        if len(self.points) < 2:
            print("[Mesh][Behaviour:Patrol] WARNING: Patrol requires at least two points")
            self._disabled = True

    def update(self, dt: float) -> None:
        if self._disabled:
            return

        if not self.points:
            return

        target = self.points[self.current_index]
        dx = target[0] - self.entity.center_x
        dy = target[1] - self.entity.center_y
        dist = math.hypot(dx, dy)
        if dist < 1e-3:
            self._advance()
            return

        step = self.speed * dt
        if step <= 0:
            return

        norm_x = dx / dist
        norm_y = dy / dist
        step = min(step, dist)  # this frame's distance, never past the point

        mover = getattr(self.window, "move_entity_with_collision", None)
        if callable(mover):
            mover(self.entity, norm_x * step, norm_y * step)  # it moves by exactly what it's given
        else:  # Fallback if window lacks helper.
            self.entity.center_x += norm_x * step
            self.entity.center_y += norm_y * step

        remaining = math.hypot(target[0] - self.entity.center_x, target[1] - self.entity.center_y)
        if remaining <= max(1.0, step * 0.25):
            self.entity.center_x = target[0]
            self.entity.center_y = target[1]
            self._advance()

    def _advance(self) -> None:
        self.current_index = (self.current_index + 1) % len(self.points)
