"""A campfire (Milestone 23B): the object is a fire in an HD-2D room (``engine.fire``).

It registers its fire with the room as it is made; the HD-2D renderer draws its logs and flames, its embers, sparks
and smoke, and lights the ground, trees and walls round it with a flickering warm light. Off (``enabled`` false):
only the cold logs. A 2D room draws none of it."""

from __future__ import annotations

from typing import Any

from engine import fire as fire_mod

from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "Campfire",
    description="A campfire in an HD-2D room: flames, embers, smoke and a warm light (Studio: the Campfire object).",
    config_fields=[
        {"name": "enabled", "description": "Burning (off: cold logs)", "type": "bool", "default": True},
        {"name": "size", "description": "The flames' size (0.5-1.5)", "type": "float", "default": 1.0},
        {"name": "smoke", "description": "Smoke rises from it", "type": "bool", "default": True},
        {"name": "light", "description": "Its light's strength (0-3)", "type": "float", "default": 1.0},
        {"name": "light_radius", "description": "How far its light reaches (px)", "type": "float", "default": 192.0},
    ],
)
class Campfire(Behaviour):
    PARAM_DEFS = {  # what engine.fire.parse_fire reads (checked there; Studio and AI: project_ops.set_campfire)
        "enabled": ParamDef(bool, default=True, description="Burning (off: cold logs)"),
        "size": ParamDef(float, default=1.0, description="The flames' size (0.5-1.5)"),
        "smoke": ParamDef(bool, default=True, description="Smoke rises from it"),
        "light": ParamDef(float, default=1.0, description="Its light's strength (0-3)"),
        "light_radius": ParamDef(float, default=192.0, description="How far its light reaches (px)"),
    }

    def __init__(self, entity: Any, window: Any, **config: Any) -> None:
        settings = {k: v for k, v in config.items() if k in self.PARAM_DEFS}
        super().__init__(entity, window, **settings)
        if not getattr(entity, "mesh_entity_data", {}).get("sprite"):
            entity.mesh_drawn = False  # the fire is its picture
        try:
            self.fire = fire_mod.parse_fire(settings)
        except fire_mod.FireError as exc:
            from engine.logging_tools import get_logger  # noqa: PLC0415

            get_logger(__name__).error("[Mesh][Fire] %s: fire off: %s", getattr(entity, "mesh_name", "Campfire"), exc)
            return
        fire_mod.register(window, entity, self.fire)
