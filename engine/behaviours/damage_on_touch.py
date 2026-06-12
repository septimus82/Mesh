"""Damage-on-contact behaviour for Mesh Engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

import engine.optional_arcade as optional_arcade

from .base import Behaviour, ParamDef
from .registry import register_behaviour

if TYPE_CHECKING:  # pragma: no cover - typing only
    from arcade import Sprite

    from engine.game import GameWindow


@register_behaviour(
    "DamageOnTouch",
    description="Emits a damage event when colliding with the target sprite.",
    config_fields=[
        {
            "name": "target_name",
            "description": "Name of the sprite that should receive damage",
            "type": "string",
            "default": "player",
        },
        {
            "name": "damage",
            "description": "Damage value applied on contact",
            "type": "float",
            "default": 1.0,
        },
        {
            "name": "once",
            "description": "If true, damage applies only on the first hit",
            "type": "bool",
            "default": False,
        },
        {
            "name": "destroy_on_hit",
            "description": "Remove the damaging sprite after contact",
            "type": "bool",
            "default": False,
        },
    ],
)
class DamageOnTouch(Behaviour):
    """Generic contact-damage behaviour."""

    PARAM_DEFS = {
        "target_name": ParamDef(str, default="player", description="Name of the sprite that should receive damage"),
        "damage": ParamDef(float, default=1.0, description="Damage value applied on contact"),
        "once": ParamDef(bool, default=False, description="If true, damage applies only on the first hit"),
        "destroy_on_hit": ParamDef(bool, default=False, description="Remove the damaging sprite after contact"),
    }

    def __init__(self, entity: "Sprite", window: "GameWindow", **config) -> None:
        super().__init__(entity, window, **config)

        self.target_name = self.config.get("target_name", "player")
        self.damage = float(self.config.get("damage", 1.0))
        self.once = bool(self.config.get("once", False))
        self.destroy_on_hit = bool(self.config.get("destroy_on_hit", False))
        self._already_triggered: bool = False

    def update(self, dt: float) -> None:  # noqa: D401 ARG002
        """Emit damage events when touching the configured target entity."""
        if self._already_triggered and self.once:
            return

        if not self.target_name:
            return

        target = self.window.find_sprite_by_name(self.target_name)
        if not target:
            return

        if not optional_arcade.arcade.check_for_collision(self.entity, target):
            return

        if not self.window.should_collide(self.entity, target):
            return

        self.window.on_damage(self.entity, target, self.damage)

        if self.once:
            self._already_triggered = True

        if self.destroy_on_hit:
            self.entity.remove_from_sprite_lists()
