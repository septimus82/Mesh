"""Collectible behaviour for Mesh Engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Behaviour, ParamDef
from .registry import register_behaviour

if TYPE_CHECKING:  # pragma: no cover - typing only
    from arcade import Sprite

    from engine.game import GameWindow
import engine.optional_arcade as optional_arcade
from engine.hd2d.world import same_level


@register_behaviour(
    "Collectible",
    description="Automatically collects when a named entity overlaps the sprite.",
    config_fields=[
        {
            "name": "collect_by_name",
            "description": "Name of the sprite allowed to pick this up",
            "type": "string",
            "default": "player",
        },
        {
            "name": "auto_remove",
            "description": "Whether to remove the sprite after collection",
            "type": "bool",
            "default": True,
        },
    ],
)
class Collectible(Behaviour):
    """Generic collectible behaviour."""

    PARAM_DEFS = {
        "collect_by_name": ParamDef(str, default="player", description="Name of the sprite allowed to pick this up"),
        "auto_remove": ParamDef(bool, default=True, description="Whether to remove the sprite after collection"),
    }

    def __init__(self, entity: "Sprite", window: "GameWindow", **config) -> None:
        super().__init__(entity, window, **config)
        self.collect_by_name = self.config.get("collect_by_name", "player")
        self.auto_remove = bool(self.config.get("auto_remove", True))

    def update(self, dt: float) -> None:  # noqa: D401 ARG002
        """Check if the configured collector overlaps this entity."""
        if not self.collect_by_name:
            return

        collector = self.window.find_sprite_by_name(self.collect_by_name)

        if not collector:
            return

        if not optional_arcade.arcade.check_for_collision(self.entity, collector):
            return

        if not same_level(getattr(self.window, "hd2d_world", None), self.entity, collector):
            return  # an HD-2D room: on another floor (engine.hd2d.world.same_level)

        if not self.window.should_collide(self.entity, collector):
            return

        self.window.on_collectible_picked(self.entity, collector)

        if self.auto_remove:
            self.entity.remove_from_sprite_lists()
