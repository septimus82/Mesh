"""Behaviour that follows a named target sprite."""

from __future__ import annotations

import math

from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "FollowTarget",
    description="Moves toward another sprite using a constant speed.",
    config_fields=[
        {
            "name": "follow_target",
            "description": "Name of the sprite to follow",
            "type": "string",
            "default": "",
        },
        {
            "name": "follow_speed",
            "description": "Movement speed in units per second",
            "type": "float",
            "default": 100.0,
        },
    ],
)
class FollowBehaviour(Behaviour):
    """Moves the sprite toward another sprite each frame."""

    PARAM_DEFS = {
        "follow_target": ParamDef(str, default="", description="Name of the sprite to follow"),
        "follow_speed": ParamDef(float, default=100.0, description="Movement speed in units per second"),
    }

    def __init__(self, entity, window, **config) -> None:
        super().__init__(entity, window, **config)
        target_name = str(self.config.get("follow_target", "")).strip()
        self.target_name: str | None = target_name or None
        self.speed: float = float(self.config.get("follow_speed", 100.0))
        self._warned_missing = False

        if not self.target_name:
            print("[Mesh][Behaviour:Follow] WARNING: Missing follow_target")
            self._disabled = True
        else:
            self._disabled = False

    def update(self, dt: float) -> None:
        if getattr(self, "_disabled", False):
            return

        target = self._resolve_target()
        if target is None:
            return

        dx = target.center_x - self.entity.center_x
        dy = target.center_y - self.entity.center_y
        dist = math.hypot(dx, dy)
        if dist < 1e-4:
            return

        step = self.speed * dt
        if step <= 0:
            return

        norm_x = dx / dist
        norm_y = dy / dist
        move_speed = self.speed
        if step > dist and dt > 0:
            move_speed = min(self.speed, dist / dt)

        mover = getattr(self.window, "move_entity_with_collision", None)
        if callable(mover):
            mover(self.entity, norm_x * move_speed, norm_y * move_speed, dt)
        else:
            self.entity.center_x += norm_x * min(step, dist)
            self.entity.center_y += norm_y * min(step, dist)

        remaining = math.hypot(target.center_x - self.entity.center_x, target.center_y - self.entity.center_y)
        if remaining <= max(1.0, move_speed * dt * 0.25):
            self.entity.center_x = target.center_x
            self.entity.center_y = target.center_y

    def _resolve_target(self):
        if not self.target_name:
            return None

        target = self.window.find_sprite_by_name(self.target_name)
        if target is None and not self._warned_missing:
            print(f"[Mesh][Behaviour:Follow] WARNING: Target '{self.target_name}' not found")
            self._warned_missing = True
            self._disabled = True
            return None

        return target
