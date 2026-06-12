"""Hitbox behaviour for Mesh Engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

import engine.optional_arcade as optional_arcade
from engine.combat_constants import (
    EVENT_COMBAT_ATTACK,
    KEY_AMOUNT,
    KEY_SOURCE,
    KEY_TARGET,
)
from engine.event_emit import emit_gameplay_event

from .base import Behaviour, ParamDef
from .registry import register_behaviour

if TYPE_CHECKING:
    from arcade import Sprite

    from engine.game import GameWindow


def _try_rumble(window: object, intensity: float, duration_s: float) -> None:
    input_controller = getattr(window, "input_controller", None)
    manager = getattr(input_controller, "manager", None) if input_controller is not None else None
    rumble = getattr(manager, "rumble", None) if manager is not None else None
    if callable(rumble):
        try:
            rumble(float(intensity), float(duration_s), 0)
        except Exception:
            return


@register_behaviour(
    "Hitbox",
    description="Temporary entity that deals damage on contact.",
    config_fields=[
        {
            "name": "damage",
            "description": "Damage to deal",
            "type": "float",
            "default": 1.0,
        },
        {
            "name": "target_tag",
            "description": "Tag of entities to damage",
            "type": "string",
            "default": "enemy",
        },
        {
            "name": "duration",
            "description": "How long the hitbox lasts (seconds)",
            "type": "float",
            "default": 0.2,
        },
        {
            "name": "width",
            "description": "Width of the hitbox",
            "type": "float",
            "default": 32.0,
        },
        {
            "name": "height",
            "description": "Height of the hitbox",
            "type": "float",
            "default": 32.0,
        },
    ],
)
class Hitbox(Behaviour):
    """Logic for a short-lived damage zone."""

    PARAM_DEFS = {
        "damage": ParamDef(float, default=1.0, description="Damage to deal"),
        "target_tag": ParamDef(str, default="enemy", description="Tag of entities to damage"),
        "duration": ParamDef(float, default=0.2, description="How long the hitbox lasts"),
        "width": ParamDef(float, default=32.0, description="Width of the hitbox"),
        "height": ParamDef(float, default=32.0, description="Height of the hitbox"),
    }

    def __init__(self, entity: "Sprite", window: "GameWindow", **config) -> None:
        super().__init__(entity, window, **config)
        self.damage = float(self.config.get("damage", 1.0))
        self.target_tag = str(self.config.get("target_tag", "enemy"))
        self.duration = float(self.config.get("duration", 0.2))
        self.width = float(self.config.get("width", 32.0))
        self.height = float(self.config.get("height", 32.0))

        self._timer = 0.0
        self._hit_list: set[Sprite] = set()

    def update(self, dt: float) -> None:
        self._timer += dt
        if self._timer >= self.duration:
            self.entity.remove_from_sprite_lists()
            return

        # Check collisions
        scene_controller = getattr(self.window, "scene_controller", None)
        if not scene_controller:
            return

        # Find candidates
        candidates = []
        for sprite in scene_controller.all_sprites:
            if sprite == self.entity:
                continue
            if getattr(sprite, "mesh_tag", "") == self.target_tag:
                candidates.append(sprite)

        if not candidates:
            return

        # Check collision

        sprite_list = optional_arcade.arcade.SpriteList()
        for candidate in candidates:
            sprite_list.append(candidate)
        hits = optional_arcade.arcade.check_for_collision_with_list(self.entity, sprite_list)
        for hit in hits:
            if hit in self._hit_list:
                continue

            self._hit_list.add(hit)
            self._apply_damage(hit)

    def _apply_damage(self, target: Sprite) -> None:
        source_name = str(getattr(self.entity, "mesh_name", "") or "").strip() or "hitbox"
        target_name = str(getattr(target, "mesh_name", "") or "").strip() or "<unnamed>"
        emit_gameplay_event(
            self.window,
            EVENT_COMBAT_ATTACK,
            {
                KEY_SOURCE: source_name,
                KEY_TARGET: target_name,
                KEY_AMOUNT: float(self.damage),
                "type": "melee",
            },
            source_entity_id=str(getattr(self.entity, "mesh_id", "") or ""),
            source_behaviour="Hitbox",
        )
        # Look for Health behaviour
        behaviours = getattr(target, "mesh_behaviours_runtime", [])
        for behaviour in behaviours:
            if hasattr(behaviour, "apply_damage"):
                behaviour.apply_damage(
                    self.damage,
                    source_entity=source_name,
                    source_behaviour="Hitbox",
                )

                # Audio feedback
                if hasattr(self.window, "audio"):
                    self.window.audio.play_world_sfx(
                        "assets/sounds/hit.wav",
                        world_pos=(float(target.center_x), float(target.center_y)),
                        window=self.window,
                        base_volume=0.6,
                        profile="melee",
                    )
                _try_rumble(self.window, 0.5, 0.06)

                # Visual feedback?
                # self.window.spawn_particle(...)
                break
