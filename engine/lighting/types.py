"""Lighting type helpers extracted from the lighting module.

These remain import-safe and do not depend on Arcade at import time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .flicker import FlickerNoise


@dataclass
class DynamicLightHandle:
    """Handle for a light dynamically attached to a moving entity.

    Dynamic lights automatically update their position based on the owner
    sprite's position plus configured offsets. They support flicker effects,
    light cookies (texture patterns), and volumetric light shafts.

    Attributes:
        owner: The sprite this light follows (position source).
        light: The underlying Arcade Light object.
        offset_x: Horizontal offset from owner center in pixels.
        offset_y: Vertical offset from owner center in pixels.
        base_radius: Light radius in pixels (before flicker modulation).
        base_color: Light color as (R, G, B, A) tuple.
        color_rgba: Optional override color (for runtime color changes).
        flicker_enabled: Whether flicker effect is active.
        flicker_seed: RNG seed for deterministic flicker.
        flicker_speed: Flicker animation speed multiplier.
        flicker_amount: Flicker intensity (0.0-1.0 scale).
        flicker_radius_px: Optional flicker effect on radius.
        flicker_intensity: Optional flicker effect on brightness.
        cookie_id: Asset path to light cookie texture.
        cookie_scale: Scale factor for cookie texture.
        cookie_rotation_deg: Cookie rotation in degrees.
        cookie_offset_px: Cookie texture offset as (x, y).
        shafts_enabled: Enable volumetric light shafts.
        shafts_length_px: Length of light shaft rays.
        shafts_width_px: Width of light shaft cone.
        shafts_rotation_deg: Shaft direction in degrees.
        shafts_alpha: Shaft opacity (0.0-1.0).
        shafts_noise_speed: Animated noise speed for shafts.
        shafts_noise_amount: Noise intensity for shaft edges.

    Example::

        handle = DynamicLightHandle(
            owner=player_sprite,
            light=arcade_light,
            offset_y=10,
            base_radius=120,
            base_color=(255, 255, 200, 255),
            flicker_enabled=True,
            flicker_amount=0.1,
        )
    """

    owner: Any
    light: Any
    offset_x: float = 0.0
    offset_y: float = 0.0
    base_radius: float = 0.0
    base_color: tuple[int, int, int, int] = (255, 255, 255, 255)
    color_rgba: tuple[int, int, int, int] | None = None
    flicker_enabled: bool = False
    flicker_seed: int | None = None
    flicker_speed: float = 1.0
    flicker_amount: float = 0.0
    flicker_radius_px: float | None = None
    flicker_intensity: float | None = None
    cookie_id: str | None = None
    cookie_scale: float = 1.0
    cookie_rotation_deg: float = 0.0
    cookie_offset_px: tuple[float, float] = (0.0, 0.0)
    shafts_enabled: bool = False
    shafts_length_px: float = 220.0
    shafts_width_px: float = 140.0
    shafts_rotation_deg: float = 0.0
    shafts_alpha: float = 0.35
    shafts_noise_speed: float = 0.08
    shafts_noise_amount: float = 0.15


@dataclass(slots=True)
class _FlickerLightState:
    light: Any
    base_radius: float
    base_color: tuple[int, int, int, int]
    noise: "FlickerNoise"
    speed: float
    amount: float
    radius_px: float | None
    intensity: float | None


class _LayerContext:
    def __init__(self, layer: Any) -> None:
        self.layer = layer

    def __enter__(self) -> Any:
        if hasattr(self.layer, "use"):
            self.layer.use()
        return self.layer

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if hasattr(self.layer, "clear"):
            self.layer.clear()
        return None
