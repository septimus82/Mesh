"""Ranged attack AI behaviour."""

from __future__ import annotations

import math
import time

from engine.combat_constants import (
    EVENT_COMBAT_ATTACK,
    EVENT_PROJECTILE_FIRED,
)
from engine.event_emit import emit_gameplay_event
from engine.behaviours.base import Behaviour, ParamDef
from engine.behaviours.registry import register_behaviour


@register_behaviour(
    "RangedAttackAI",
    description="Attacks the player from a distance.",
    config_fields=[
        {
            "name": "attack_range",
            "description": "Maximum distance to attack from",
            "type": "float",
            "default": 200.0,
        },
        {
            "name": "attack_cooldown",
            "description": "Time between attacks in seconds",
            "type": "float",
            "default": 2.0,
        },
        {
            "name": "projectile_speed",
            "description": "Speed of the projectile",
            "type": "float",
            "default": 300.0,
        },
    ],
)
class RangedAttackAI(Behaviour):
    """Simple ranged enemy AI."""

    PARAM_DEFS = {
        "attack_range": ParamDef(float, default=200.0, description="Maximum distance to attack from"),
        "attack_cooldown": ParamDef(float, default=2.0, description="Time between attacks in seconds"),
        "projectile_speed": ParamDef(float, default=300.0, description="Speed of the projectile"),
    }

    def __init__(self, entity, window, **config) -> None:
        super().__init__(entity, window, **config)
        self.attack_range = config.get("attack_range", 200.0)
        self.attack_cooldown = config.get("attack_cooldown", 2.0)
        self.projectile_speed = config.get("projectile_speed", 300.0)
        self.last_attack_time = 0.0
        self.player = None

    def update(self, dt: float) -> None:
        if not self.player:
            self.player = self._find_player()
            if not self.player:
                return

        # Calculate distance to player
        dx = self.player.x - self.entity.x
        dy = self.player.y - self.entity.y
        dist_sq = dx * dx + dy * dy

        if dist_sq <= self.attack_range * self.attack_range:
            current_time = time.time()
            if current_time - self.last_attack_time >= self.attack_cooldown:
                self._attack(dx, dy)
                self.last_attack_time = current_time

    def _find_player(self):
        # Simple lookup in current scene entities
        # Assuming window.current_scene.entities is accessible
        if hasattr(self.window, "current_scene") and self.window.current_scene:
            for entity in self.window.current_scene.entities:
                if entity.tag == "player":
                    return entity
        return None

    def _attack(self, dx: float, dy: float) -> None:
        # Normalize direction
        dist = math.sqrt(dx * dx + dy * dy)
        if dist > 0:
            dir_x = dx / dist
            dir_y = dy / dist
        else:
            dir_x = 1.0
            dir_y = 0.0

        emit_gameplay_event(
            self.window,
            EVENT_PROJECTILE_FIRED,
            {
                "source": self.entity.name,
                "x": self.entity.x,
                "y": self.entity.y,
                "dir_x": dir_x,
                "dir_y": dir_y,
                "speed": self.projectile_speed,
            },
            source_entity_id=str(getattr(self.entity, "mesh_id", "") or ""),
            source_behaviour="RangedAttackAI",
        )
        # Also emit combat event for quests
        emit_gameplay_event(
            self.window,
            EVENT_COMBAT_ATTACK,
            {
                "attacker": self.entity.name,
                "target": "Player",
                "type": "ranged",
            },
            source_entity_id=str(getattr(self.entity, "mesh_id", "") or ""),
            source_behaviour="RangedAttackAI",
        )

