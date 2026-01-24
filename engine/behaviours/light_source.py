"""Behaviour that attaches a dynamic light to an entity."""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from arcade import Sprite

from .base import Behaviour, ParamDef
from .registry import register_behaviour
from ..lighting.flicker import FlickerNoise, apply_light_flicker


@register_behaviour(
    "LightSource",
    description="Adds a dynamic light that follows the entity.",
    config_fields=[
        {"name": "radius", "type": "float", "default": 160.0},
        {"name": "color", "type": "string", "default": "#ffffff"},
        {"name": "color_rgba", "type": "array", "default": None},
        {"name": "mode", "type": "string", "default": "soft"},
        {"name": "offset_x", "type": "float", "default": 0.0},
        {"name": "offset_y", "type": "float", "default": 0.0},
        {"name": "enabled", "type": "bool", "default": True},
        {"name": "cookie_id", "type": "string", "default": None},
        {"name": "cookie_scale", "type": "float", "default": 1.0},
        {"name": "cookie_rotation_deg", "type": "float", "default": 0.0},
        {"name": "cookie_offset_px", "type": "array", "default": None},
        {"name": "flicker_enabled", "type": "bool", "default": False, "description": "Whether the light radius should flicker over time."},
        {"name": "flicker_seed", "type": "int", "default": None},
        {"name": "flicker_amount", "type": "float", "default": 20.0, "description": "Flicker intensity scale (0..1); values >1 treated as legacy pixel radius."},
        {"name": "flicker_radius_px", "type": "float", "default": None, "description": "Override radius flicker in pixels (legacy)."},
        {"name": "flicker_intensity", "type": "float", "default": None, "description": "Override intensity flicker scale (0..1)."},
        {"name": "flicker_speed", "type": "float", "default": 5.0, "description": "Flicker speed in cycles per second (roughly)."},
        {"name": "shafts_enabled", "type": "bool", "default": False},
        {"name": "shafts_length_px", "type": "float", "default": 220.0},
        {"name": "shafts_width_px", "type": "float", "default": 140.0},
        {"name": "shafts_rotation_deg", "type": "float", "default": 0.0},
        {"name": "shafts_alpha", "type": "float", "default": 0.35},
        {"name": "shafts_noise_speed", "type": "float", "default": 0.08},
        {"name": "shafts_noise_amount", "type": "float", "default": 0.15},
    ],
)
class LightSource(Behaviour):
    """Dynamic light tied to an entity."""

    PARAM_DEFS = {
        "radius": ParamDef(float, default=160.0, description="Light radius in pixels"),
        "color": ParamDef(str, default="#ffffff", description="Light color (hex or arcade-compatible)"),
        "color_rgba": ParamDef(list, default=[], description="Light color as RGBA array"),
        "mode": ParamDef(str, default="soft", description="Light mode (soft|hard)"),
        "offset_x": ParamDef(float, default=0.0, description="X offset from entity center"),
        "offset_y": ParamDef(float, default=0.0, description="Y offset from entity center"),
        "enabled": ParamDef(bool, default=True, description="Whether the light is active"),
        "cookie_id": ParamDef(str, default="", description="Cookie texture id/path"),
        "cookie_scale": ParamDef(float, default=1.0, description="Cookie scale relative to light size"),
        "cookie_rotation_deg": ParamDef(float, default=0.0, description="Cookie rotation in degrees"),
        "cookie_offset_px": ParamDef(list, default=[], description="Cookie offset in pixels"),
        "flicker_enabled": ParamDef(bool, default=False, description="Enable animated flicker"),
        "flicker_seed": ParamDef(int, default=0, description="Deterministic flicker seed (0=random)"),
        "flicker_amount": ParamDef(float, default=20.0, description="Flicker intensity scale (0..1); values >1 treated as legacy pixel radius"),
        "flicker_radius_px": ParamDef(float, default=0.0, description="Override radius flicker in pixels"),
        "flicker_intensity": ParamDef(float, default=0.0, description="Override intensity flicker scale (0..1)"),
        "flicker_speed": ParamDef(float, default=5.0, description="Flicker cycles per second"),
        "shafts_enabled": ParamDef(bool, default=False, description="Enable light shafts"),
        "shafts_length_px": ParamDef(float, default=220.0, description="Light shafts length in pixels"),
        "shafts_width_px": ParamDef(float, default=140.0, description="Light shafts width in pixels"),
        "shafts_rotation_deg": ParamDef(float, default=0.0, description="Light shafts rotation in degrees"),
        "shafts_alpha": ParamDef(float, default=0.35, description="Base shafts alpha (0..1)"),
        "shafts_noise_speed": ParamDef(float, default=0.08, description="Shafts noise speed"),
        "shafts_noise_amount": ParamDef(float, default=0.15, description="Shafts noise amount (0..1)"),
    }

    def __init__(self, entity: Sprite, window, **config: Any) -> None:  # type: ignore[override]
        super().__init__(entity, window, **config)
        self._light_handle = None
        enabled = bool(self.config.get("enabled", True))
        lighting = getattr(window, "lighting", None)
        if enabled and lighting is not None:
            flicker_enabled = bool(self.config.get("flicker_enabled", False))
            flicker_amount = float(self.config.get("flicker_amount", 0.0))
            flicker_radius_px = self.config.get("flicker_radius_px")
            if flicker_radius_px is None and flicker_amount > 1.0:
                flicker_radius_px = flicker_amount
                flicker_amount = 0.0
            self._light_handle = lighting.register_dynamic_light(
                owner=entity,
                radius=float(self.config.get("radius", 160.0)),
                color=self.config.get("color", "#ffffff"),
                color_rgba=self.config.get("color_rgba"),
                mode=str(self.config.get("mode", "soft")),
                offset_x=float(self.config.get("offset_x", 0.0)),
                offset_y=float(self.config.get("offset_y", 0.0)),
                cookie_id=self.config.get("cookie_id"),
                cookie_scale=float(self.config.get("cookie_scale", 1.0)),
                cookie_rotation_deg=float(self.config.get("cookie_rotation_deg", 0.0)),
                cookie_offset_px=self.config.get("cookie_offset_px"),
                flicker_enabled=flicker_enabled,
                flicker_seed=self.config.get("flicker_seed"),
                flicker_speed=float(self.config.get("flicker_speed", 5.0)),
                flicker_amount=flicker_amount,
                flicker_radius_px=flicker_radius_px,
                flicker_intensity=self.config.get("flicker_intensity"),
                shafts_enabled=bool(self.config.get("shafts_enabled", False)),
                shafts_length_px=float(self.config.get("shafts_length_px", 220.0)),
                shafts_width_px=float(self.config.get("shafts_width_px", 140.0)),
                shafts_rotation_deg=float(self.config.get("shafts_rotation_deg", 0.0)),
                shafts_alpha=float(self.config.get("shafts_alpha", 0.35)),
                shafts_noise_speed=float(self.config.get("shafts_noise_speed", 0.08)),
                shafts_noise_amount=float(self.config.get("shafts_noise_amount", 0.15)),
            )
        self._base_radius = float(self.config.get("radius", 160.0))
        self._flicker_enabled = bool(self.config.get("flicker_enabled", False))
        self._flicker_amount = max(0.0, float(self.config.get("flicker_amount", 0.0)))
        self._flicker_speed = max(0.0, float(self.config.get("flicker_speed", 5.0)))
        self._flicker_phase = 0.0
        self._uses_manager_flicker = bool(self._light_handle and self._flicker_enabled)
        self._legacy_flicker_time = 0.0
        self._legacy_flicker_noise: FlickerNoise | None = None
        self._legacy_flicker_seed: int | None = None

    def _legacy_flicker_seed_value(self) -> int | None:
        if "flicker_seed" not in self._explicit_params:
            return None
        raw = self.config.get("flicker_seed")
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    def _legacy_base_color(self) -> tuple[int, int, int, int]:
        handle = self._light_handle
        base = getattr(handle, "base_color", None) if handle is not None else None
        if isinstance(base, (tuple, list)) and len(base) >= 3:
            r = int(round(base[0]))
            g = int(round(base[1]))
            b = int(round(base[2]))
            a = int(round(base[3])) if len(base) >= 4 else 255
            return (
                max(0, min(255, r)),
                max(0, min(255, g)),
                max(0, min(255, b)),
                max(0, min(255, a)),
            )
        return (255, 255, 255, 255)

    def update(self, dt: float) -> None:  # noqa: D401
        """Update light flicker animation."""
        if self._uses_manager_flicker:
            return
        if not (self._flicker_enabled and self._light_handle and self._flicker_amount > 0.0 and self._flicker_speed > 0.0):
            return
        seed_value = self._legacy_flicker_seed_value()
        if seed_value is not None:
            if self._legacy_flicker_seed != seed_value:
                self._legacy_flicker_seed = seed_value
                self._legacy_flicker_noise = FlickerNoise(seed_value)
                self._legacy_flicker_time = 0.0
            self._legacy_flicker_time += float(dt)
            noise = self._legacy_flicker_noise
            if noise is None:
                return
            radius, color = apply_light_flicker(
                base_radius=self._base_radius,
                base_color=self._legacy_base_color(),
                noise=noise,
                time_s=self._legacy_flicker_time,
                speed=self._flicker_speed,
                amount=self._flicker_amount,
                radius_px=self.config.get("flicker_radius_px"),
                intensity=self.config.get("flicker_intensity"),
            )
        else:
            if self._legacy_flicker_seed is not None:
                self._legacy_flicker_seed = None
                self._legacy_flicker_noise = None
                self._legacy_flicker_time = 0.0
            self._flicker_phase += float(dt) * self._flicker_speed * 2.0 * math.pi
            sine_component = math.sin(self._flicker_phase)
            jitter_component = random.uniform(-1.0, 1.0)
            blend = sine_component * 0.5 + jitter_component * 0.5
            radius = max(0.0, self._base_radius + blend * self._flicker_amount)
            color = None
        light = getattr(self._light_handle, "light", None)
        if light is None:
            return
        if hasattr(light, "radius"):
            try:
                light.radius = radius
            except Exception as exc:  # noqa: BLE001
                if not getattr(self, "_mesh_light_radius_error_logged", False):
                    print(f"[Mesh][LightSource] ERROR setting light radius: {exc}")
                    setattr(self, "_mesh_light_radius_error_logged", True)
        if color is not None and hasattr(light, "color"):
            try:
                light.color = color
            except Exception as exc:  # noqa: BLE001
                if not getattr(self, "_mesh_light_color_error_logged", False):
                    print(f"[Mesh][LightSource] ERROR setting light color: {exc}")
                    setattr(self, "_mesh_light_color_error_logged", True)
