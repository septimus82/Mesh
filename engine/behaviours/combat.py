"""Combat behaviour for Mesh Engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

from engine.swallowed_exceptions import _log_swallow

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
    "Combat",
    description="Allows an entity to attack and deal damage.",
    config_fields=[
        {
            "name": "damage",
            "description": "Damage dealt per attack",
            "type": "float",
            "default": 1.0,
        },
        {
            "name": "cooldown",
            "description": "Time in seconds between attacks",
            "type": "float",
            "default": 1.0,
        },
        {
            "name": "range",
            "description": "Attack range (offset from center)",
            "type": "float",
            "default": 32.0,
        },
        {
            "name": "hitbox_size",
            "description": "Size of the damage area",
            "type": "float",
            "default": 32.0,
        },
        {
            "name": "target_tag",
            "description": "Tag of entities to damage (e.g. 'enemy')",
            "type": "string",
            "default": "enemy",
        },
        {
            "name": "attack_anim",
            "description": "Animation state to play on attack",
            "type": "string",
            "default": "attack",
        },
        {
            "name": "attack_sound",
            "description": "Sound to play on attack",
            "type": "string",
            "default": "assets/sounds/attack.wav",
        },
    ],
)
class Combat(Behaviour):
    """Manages attack cooldowns and hitbox spawning."""

    PARAM_DEFS = {
        "damage": ParamDef(float, default=1.0, description="Damage dealt per attack"),
        "cooldown": ParamDef(float, default=1.0, description="Time in seconds between attacks"),
        "range": ParamDef(float, default=32.0, description="Attack range"),
        "hitbox_size": ParamDef(float, default=32.0, description="Size of the damage area"),
        "target_tag": ParamDef(str, default="enemy", description="Tag of entities to damage"),
        "attack_anim": ParamDef(str, default="attack", description="Animation state to play on attack"),
        "attack_sound": ParamDef(str, default="assets/sounds/attack.wav", description="Sound to play on attack"),
    }

    def __init__(self, entity: "Sprite", window: "GameWindow", **config) -> None:
        super().__init__(entity, window, **config)
        cfg = getattr(window, "engine_config", None)
        self._use_player_stats = bool(getattr(cfg, "player_stats_enabled", True))
        self.damage = float(self.config.get("damage", 1.0))
        self.cooldown = float(self.config.get("cooldown", 1.0))
        self.range = float(self.config.get("range", 32.0))
        self.hitbox_size = float(self.config.get("hitbox_size", 32.0))
        self.target_tag = str(self.config.get("target_tag", "enemy"))
        self.attack_anim = str(self.config.get("attack_anim", "attack"))
        if self._use_player_stats and "damage" not in self._explicit_params and getattr(entity, "mesh_tag", "") == "player":
            try:
                gs = getattr(window, "game_state_controller", None)
                if gs is not None:
                    stats = gs.get_player_stats()
                    self.damage = float(stats.get("attack", self.damage))
            except Exception as exc:  # noqa: BLE001  # REASON: player stat lookup failures should not block combat behaviour initialization
                if not getattr(self, "_mesh_player_stats_damage_error_logged", False):
                    print(f"[Mesh][Combat] ERROR applying player stats damage override: {exc}")
                    setattr(self, "_mesh_player_stats_damage_error_logged", True)

        self._cooldown_timer = 0.0

    def update(self, dt: float) -> None:
        if self._cooldown_timer > 0:
            self._cooldown_timer -= dt

    def _entity_name(self) -> str:
        for attr_name in ("mesh_name", "name"):
            raw_name = getattr(self.entity, attr_name, None)
            if isinstance(raw_name, str):
                name = raw_name.strip()
                if name:
                    return name
        return "<unnamed>"

    def attack(self) -> bool:
        """Attempt to perform an attack. Returns True if successful."""
        if self._cooldown_timer > 0:
            return False

        self._cooldown_timer = self.cooldown

        # Play animation
        animator = getattr(self.entity, "mesh_animator", None)
        if animator:
            from ..animation_state import request_animation_state
            request_animation_state(self.entity, self.attack_anim, priority=10, ttl=0.5)

        # Spawn hitbox
        self._spawn_hitbox()

        # Play sound
        if hasattr(self.window, "audio"):
            sound_path = self.config.get("attack_sound", "assets/sounds/attack.wav")
            self.window.audio.play_world_sfx(
                sound_path,
                world_pos=(float(self.entity.center_x), float(self.entity.center_y)),
                window=self.window,
                base_volume=0.5,
                profile="attack",
            )
        _try_rumble(self.window, 0.2, 0.03)

        return True

    def _spawn_hitbox(self) -> None:
        import math

        from ..inventory import load_item_database

        # Calculate damage - start with base damage
        current_damage = self.damage

        # Check for equipped weapon bonus if player
        if getattr(self.entity, "mesh_tag", "") == "player":
            gs = getattr(self.window, "game_state_controller", None)
            if gs is not None:
                equipment = gs.get_equipment()
                weapon_id = equipment.get("weapon")
                if weapon_id:
                    try:
                        db = load_item_database()
                        item = db.get(weapon_id)
                        if item:
                            effects = item.effects or {}
                            # Use "damage" or "attack" from effects
                            bonus = float(effects.get("damage", effects.get("attack", 0)) or 0)
                            current_damage += bonus
                    except Exception:
                        _log_swallow("COMB-001", "engine/behaviours/combat.py pass-only blanket swallow")
                        pass

        # Calculate position based on facing direction
        # Assuming entity has 'angle' or we use last movement direction
        # For now, let's use the entity's angle if it exists, or default to right
        angle_rad = math.radians(getattr(self.entity, "angle", 0.0))

        # Better: Check if we have a velocity to determine direction
        dx = getattr(self.entity, "change_x", 0.0)
        dy = getattr(self.entity, "change_y", 0.0)

        if abs(dx) > 0.1 or abs(dy) > 0.1:
            angle_rad = math.atan2(dy, dx)

        offset_x = math.cos(angle_rad) * self.range
        offset_y = math.sin(angle_rad) * self.range

        hitbox_x = self.entity.center_x + offset_x
        hitbox_y = self.entity.center_y + offset_y

        # Create the hitbox entity
        # We need to inject it into the scene
        scene_controller = getattr(self.window, "scene_controller", None)
        if not scene_controller:
            return

        hitbox_data = {
            "name": f"hitbox_{self._entity_name()}",
            "x": hitbox_x,
            "y": hitbox_y,
            "layer": "entities", # Or a debug layer?
            "behaviours": ["Hitbox"],
            "behaviour_config": {
                "Hitbox": {
                    "damage": current_damage,
                    "target_tag": self.target_tag,
                    "duration": 0.2,
                    "width": self.hitbox_size,
                    "height": self.hitbox_size
                }
            }
        }

        # We need a way to create a sprite without a texture file for the hitbox (invisible or debug)
        # For now, we'll use a placeholder or create a texture programmatically?
        # SceneController._create_sprite expects a "sprite" path.
        # Let's use "assets/placeholder.png" but make it transparent or small?
        # Or we can modify SceneController to handle "no sprite" entities (just logic).

        hitbox_data["sprite"] = "assets/placeholder.png"
        hitbox_data["scale"] = self.hitbox_size / 32.0 # Assuming placeholder is 32x32? It's likely larger.
        # Actually placeholder.png size is unknown.

        sprite = scene_controller._create_sprite(hitbox_data)
        if sprite:
            sprite.alpha = 0 # Invisible
            # Add to scene
            scene_controller.add_sprite_to_layer(sprite, "entities")
