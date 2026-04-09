"""Ranged attack AI behaviour."""

from __future__ import annotations

import math
import time
from typing import TYPE_CHECKING, Any

from engine.combat_constants import (
    EVENT_COMBAT_ATTACK,
    EVENT_PROJECTILE_FIRED,
)
from engine.event_emit import emit_gameplay_event
from engine.behaviours.base import Behaviour, ParamDef
from engine.behaviours.registry import register_behaviour

if TYPE_CHECKING:
    from arcade import Sprite

    from engine.game import GameWindow


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

    def __init__(self, entity: "Sprite", window: "GameWindow", **config: Any) -> None:
        super().__init__(entity, window, **config)
        self.attack_range = float(config.get("attack_range", 200.0))
        self.attack_cooldown = float(config.get("attack_cooldown", 2.0))
        self.projectile_speed = float(config.get("projectile_speed", 300.0))
        self.last_attack_time = 0.0
        self.player: object | None = None

    def update(self, dt: float) -> None:
        if not self.player:
            self.player = self._find_player()
            if not self.player:
                return

        # Calculate distance to player
        dx = self._sprite_x(self.player) - self._sprite_x(self.entity)
        dy = self._sprite_y(self.player) - self._sprite_y(self.entity)
        dist_sq = dx * dx + dy * dy

        if dist_sq <= self.attack_range * self.attack_range:
            current_time = time.time()
            if current_time - self.last_attack_time >= self.attack_cooldown:
                self._attack(dx, dy)
                self.last_attack_time = current_time

    def _find_player(self) -> object | None:
        # Simple lookup in current scene entities
        # Assuming window.current_scene.entities is accessible
        if hasattr(self.window, "current_scene") and self.window.current_scene:
            for entity in self.window.current_scene.entities:
                candidate: object = entity
                if getattr(candidate, "tag", None) == "player":
                    return candidate
        return None

    def _sprite_x(self, sprite: object) -> float:
        for attr_name in ("x", "center_x"):
            raw_x = getattr(sprite, attr_name, None)
            if isinstance(raw_x, int | float):
                return float(raw_x)
        return 0.0

    def _sprite_y(self, sprite: object) -> float:
        for attr_name in ("y", "center_y"):
            raw_y = getattr(sprite, attr_name, None)
            if isinstance(raw_y, int | float):
                return float(raw_y)
        return 0.0

    def _entity_name(self) -> str:
        for attr_name in ("mesh_name", "name"):
            raw_name = getattr(self.entity, attr_name, None)
            if isinstance(raw_name, str):
                name = raw_name.strip()
                if name:
                    return name
        return "<unnamed>"

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
                "source": self._entity_name(),
                "x": self._sprite_x(self.entity),
                "y": self._sprite_y(self.entity),
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
                "attacker": self._entity_name(),
                "target": "Player",
                "type": "ranged",
            },
            source_entity_id=str(getattr(self.entity, "mesh_id", "") or ""),
            source_behaviour="RangedAttackAI",
        )

