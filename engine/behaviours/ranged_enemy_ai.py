"""Ranged Enemy AI behaviour for Mesh Engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Behaviour, ParamDef
from .registry import register_behaviour

if TYPE_CHECKING:
    from arcade import Sprite

    from engine.game import GameWindow


@register_behaviour(
    "RangedEnemyAI",
    description="AI that keeps distance and shoots at the target.",
    config_fields=[
        {
            "name": "target_tag",
            "description": "Tag of the target entity",
            "type": "string",
            "default": "player",
        },
        {
            "name": "detect_radius",
            "description": "Radius to detect target",
            "type": "float",
            "default": 400.0,
        },
        {
            "name": "attack_radius",
            "description": "Radius to start shooting",
            "type": "float",
            "default": 300.0,
        },
        {
            "name": "flee_radius",
            "description": "Radius to flee if target gets too close",
            "type": "float",
            "default": 150.0,
        },
        {
            "name": "speed",
            "description": "Movement speed",
            "type": "float",
            "default": 80.0,
        },
    ],
)
class RangedEnemyAI(Behaviour):
    """Simple state machine for ranged enemies."""

    PARAM_DEFS = {
        "target_tag": ParamDef(str, default="player", description="Tag of the target entity"),
        "detect_radius": ParamDef(float, default=400.0, description="Radius to detect target"),
        "attack_radius": ParamDef(float, default=300.0, description="Radius to start shooting"),
        "flee_radius": ParamDef(float, default=150.0, description="Radius to flee if target gets too close"),
        "speed": ParamDef(float, default=80.0, description="Movement speed"),
    }

    def __init__(self, entity: "Sprite", window: "GameWindow", **config) -> None:
        super().__init__(entity, window, **config)
        self.target_tag = str(self.config.get("target_tag", "player"))
        self.detect_radius = float(self.config.get("detect_radius", 400.0))
        self.attack_radius = float(self.config.get("attack_radius", 300.0))
        self.flee_radius = float(self.config.get("flee_radius", 150.0))
        self.speed = float(self.config.get("speed", 80.0))

        self._target: Sprite | None = None
        self._update_timer = 0.0

    def update(self, dt: float) -> None:
        self._update_timer -= dt
        if self._update_timer <= 0:
            self._update_timer = 0.2  # Update AI logic 5 times a second
            self._find_target()

        if not self._target:
            self.entity.change_x = 0
            self.entity.change_y = 0
            return

        # Calculate distance
        import math
        dx = self._target.center_x - self.entity.center_x
        dy = self._target.center_y - self.entity.center_y
        dist = math.sqrt(dx*dx + dy*dy)

        if dist > self.detect_radius:
            self.entity.change_x = 0
            self.entity.change_y = 0
            return

        # Movement logic
        move_x, move_y = 0.0, 0.0

        if dist < self.flee_radius:
            # Flee
            angle = math.atan2(dy, dx)
            move_x = -math.cos(angle) * self.speed
            move_y = -math.sin(angle) * self.speed
        elif dist > self.attack_radius:
            # Chase
            angle = math.atan2(dy, dx)
            move_x = math.cos(angle) * self.speed
            move_y = math.sin(angle) * self.speed
        else:
            # Hold position (or strafe?)
            move_x = 0
            move_y = 0

        # Apply movement
        self.window.move_entity_with_collision(self.entity, move_x * dt, move_y * dt)

        # Shooting logic
        if dist <= self.attack_radius:
            shooter = self._get_shooter_behaviour()
            if shooter:
                shooter.shoot_at(self._target.center_x, self._target.center_y)

    def _find_target(self) -> None:
        # Simple search for nearest target
        scene_controller = getattr(self.window, "scene_controller", None)
        if not scene_controller:
            return

        closest_dist = float('inf')
        closest_sprite = None

        for sprite in scene_controller.all_sprites:
            if getattr(sprite, "mesh_tag", "") == self.target_tag:
                dx = sprite.center_x - self.entity.center_x
                dy = sprite.center_y - self.entity.center_y
                dist = dx*dx + dy*dy
                if dist < closest_dist:
                    closest_dist = dist
                    closest_sprite = sprite

        self._target = closest_sprite

    def _get_shooter_behaviour(self):
        behaviours = getattr(self.entity, "mesh_behaviours_runtime", [])
        for b in behaviours:
            if b.__class__.__name__ == "Shooter":
                return b
        return None
