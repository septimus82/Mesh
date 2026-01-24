"""Shooter behaviour for Mesh Engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .base import Behaviour, ParamDef
from .registry import register_behaviour

if TYPE_CHECKING:
    from arcade import Sprite

    from engine.game import GameWindow


@register_behaviour(
    "Shooter",
    description="Allows an entity to shoot projectiles.",
    config_fields=[
        {
            "name": "projectile_speed",
            "description": "Speed of the projectile",
            "type": "float",
            "default": 300.0,
        },
        {
            "name": "damage",
            "description": "Damage dealt per shot",
            "type": "float",
            "default": 1.0,
        },
        {
            "name": "cooldown",
            "description": "Time in seconds between shots",
            "type": "float",
            "default": 2.0,
        },
        {
            "name": "range",
            "description": "Max range (lifetime * speed)",
            "type": "float",
            "default": 400.0,
        },
        {
            "name": "target_tag",
            "description": "Tag of entities to damage",
            "type": "string",
            "default": "player",
        },
        {
            "name": "shoot_sound",
            "description": "Sound to play on shoot",
            "type": "string",
            "default": "assets/sounds/shoot.wav",
        },
    ],
)
class Shooter(Behaviour):
    """Manages shooting cooldowns and projectile spawning."""

    PARAM_DEFS = {
        "projectile_speed": ParamDef(float, default=300.0, description="Speed of the projectile"),
        "damage": ParamDef(float, default=1.0, description="Damage dealt per shot"),
        "cooldown": ParamDef(float, default=2.0, description="Time in seconds between shots"),
        "range": ParamDef(float, default=400.0, description="Max range"),
        "target_tag": ParamDef(str, default="player", description="Tag of entities to damage"),
        "shoot_sound": ParamDef(str, default="assets/sounds/shoot.wav", description="Sound to play on shoot"),
    }

    def __init__(self, entity: "Sprite", window: "GameWindow", **config) -> None:
        super().__init__(entity, window, **config)
        self.projectile_speed = float(self.config.get("projectile_speed", 300.0))
        self.damage = float(self.config.get("damage", 1.0))
        self.cooldown = float(self.config.get("cooldown", 2.0))
        self.range = float(self.config.get("range", 400.0))
        self.target_tag = str(self.config.get("target_tag", "player"))
        self.shoot_sound = str(self.config.get("shoot_sound", "assets/sounds/shoot.wav"))

        self._cooldown_timer = 0.0

    def update(self, dt: float) -> None:
        if self._cooldown_timer > 0:
            self._cooldown_timer -= dt

    def shoot_at(self, target_x: float, target_y: float) -> bool:
        """Attempt to shoot at a target position."""
        if self._cooldown_timer > 0:
            return False

        self._cooldown_timer = self.cooldown

        # Calculate angle
        import math
        dx = target_x - self.entity.center_x
        dy = target_y - self.entity.center_y
        angle_rad = math.atan2(dy, dx)
        angle_deg = math.degrees(angle_rad)

        # Spawn projectile
        self._spawn_projectile(angle_deg)

        # Play sound
        if hasattr(self.window, "audio"):
            self.window.audio.play_sound(self.shoot_sound, volume=0.5)

        return True

    def _spawn_projectile(self, angle_deg: float) -> None:
        scene_controller = getattr(self.window, "scene_controller", None)
        if not scene_controller:
            return

        lifetime = self.range / self.projectile_speed

        projectile_data = {
            "name": f"proj_{self.entity.mesh_name}",
            "x": self.entity.center_x,
            "y": self.entity.center_y,
            "layer": "entities",
            "sprite": "assets/placeholder.png", # Should use a bullet sprite
            "scale": 0.3,
            "behaviours": ["Projectile"],
            "behaviour_config": {
                "Projectile": {
                    "speed": self.projectile_speed,
                    "damage": self.damage,
                    "target_tag": self.target_tag,
                    "lifetime": lifetime,
                    "direction": angle_deg
                }
            }
        }

        sprite = scene_controller._create_sprite(projectile_data)
        if sprite:
            sprite.color = (255, 255, 0) # Yellow bullet
            scene_controller.add_sprite_to_layer(sprite, "entities")
