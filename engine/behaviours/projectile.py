"""Projectile behaviour for Mesh Engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

import engine.optional_arcade as optional_arcade
from engine.combat_constants import (
    EVENT_PROJECTILE_HIT,
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
    "Projectile",
    description="Moves in a straight line and damages targets on impact.",
    config_fields=[
        {
            "name": "speed",
            "description": "Movement speed",
            "type": "float",
            "default": 300.0,
        },
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
            "default": "player",
        },
        {
            "name": "lifetime",
            "description": "Time in seconds before auto-destroy",
            "type": "float",
            "default": 2.0,
        },
        {
            "name": "direction",
            "description": "Direction in degrees (0 is right)",
            "type": "float",
            "default": 0.0,
        },
    ],
)
class Projectile(Behaviour):
    """Logic for a moving projectile."""

    PARAM_DEFS = {
        "speed": ParamDef(float, default=300.0, description="Movement speed"),
        "damage": ParamDef(float, default=1.0, description="Damage to deal"),
        "target_tag": ParamDef(str, default="player", description="Tag of entities to damage"),
        "lifetime": ParamDef(float, default=2.0, description="Time in seconds before auto-destroy"),
        "direction": ParamDef(float, default=0.0, description="Direction in degrees"),
    }

    def __init__(self, entity: "Sprite", window: "GameWindow", **config) -> None:
        super().__init__(entity, window, **config)
        self.speed = float(self.config.get("speed", 300.0))
        self.damage = float(self.config.get("damage", 1.0))
        self.target_tag = str(self.config.get("target_tag", "player"))
        self.lifetime = float(self.config.get("lifetime", 2.0))
        self.direction = float(self.config.get("direction", 0.0))

        import math
        rad = math.radians(self.direction)
        self.entity.change_x = math.cos(rad) * self.speed
        self.entity.change_y = math.sin(rad) * self.speed
        self.entity.angle = self.direction

    def update(self, dt: float) -> None:
        # Move (Arcade sprites don't auto-move unless we use physics engine, but SceneController calls update_animation which might not move it)
        # We need to manually move it if we aren't using a physics engine for it.
        # SceneController.update calls update() on all sprites, which applies change_x/y.
        # So it should move automatically if SceneController does `sprite.update()`.
        # Let's verify SceneController.update.

        self.lifetime -= dt
        if self.lifetime <= 0:
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
            elif getattr(sprite, "mesh_tag", "") == "terrain":
                 candidates.append(sprite)

        if not candidates:
            return

        # Check collision

        sprite_list = optional_arcade.arcade.SpriteList()
        for candidate in candidates:
            sprite_list.append(candidate)
        hits = optional_arcade.arcade.check_for_collision_with_list(self.entity, sprite_list)
        for hit in hits:
            tag = getattr(hit, "mesh_tag", "")

            if tag == "terrain":
                # Hit wall, destroy
                self.entity.remove_from_sprite_lists()
                return

            if tag == self.target_tag:
                self._apply_damage(hit)
                self.entity.remove_from_sprite_lists()
                return

    def _apply_damage(self, target: Sprite) -> None:
        source_name = str(getattr(self.entity, "mesh_name", "") or "").strip() or "projectile"
        target_name = str(getattr(target, "mesh_name", "") or "").strip() or "<unnamed>"
        emit_gameplay_event(
            self.window,
            EVENT_PROJECTILE_HIT,
            {
                KEY_SOURCE: source_name,
                KEY_TARGET: target_name,
                KEY_AMOUNT: float(self.damage),
            },
            source_entity_id=str(getattr(self.entity, "mesh_id", "") or ""),
            source_behaviour="Projectile",
        )
        # Look for Health behaviour
        behaviours = getattr(target, "mesh_behaviours_runtime", [])
        for behaviour in behaviours:
            if hasattr(behaviour, "apply_damage"):
                behaviour.apply_damage(
                    self.damage,
                    source_entity=source_name,
                    source_behaviour="Projectile",
                )

                # Audio feedback
                if hasattr(self.window, "audio"):
                    self.window.audio.play_world_sfx(
                        "assets/sounds/hit.wav",
                        world_pos=(float(target.center_x), float(target.center_y)),
                        window=self.window,
                        base_volume=0.6,
                        profile="projectile",
                    )
                _try_rumble(self.window, 0.7, 0.08)

                # Visual feedback
                if hasattr(self.window, "particle_manager"):
                    self.window.particle_manager.emit_hit_effect(target.center_x, target.center_y)
                break
