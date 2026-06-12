"""Lighting configuration dataclasses and defaults.

This module provides headless configuration types for the lighting system.
All types are pure Python dataclasses with no Arcade dependencies at import time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Default ambient color (gray-ish neutral)
DEFAULT_AMBIENT_COLOR: tuple[int, int, int, int] = (128, 128, 128, 255)

# Default limits
DEFAULT_MAX_STATIC_LIGHTS = 32
DEFAULT_MAX_DYNAMIC_LIGHTS = 16


@dataclass(slots=True, frozen=True)
class LightConfig:
    """Configuration for a single light source.

    This is a headless representation of a light that can be processed
    without GPU/Arcade dependencies. Used for deterministic planning.

    Attributes:
        light_type: Type of light ("point", "ambient", "soft", "hard").
        x: X position in world coordinates.
        y: Y position in world coordinates.
        radius: Light radius in pixels.
        color: RGBA color tuple (0-255 per channel).
        intensity: Brightness multiplier (0.0-1.0).
        mode: Shadow mode ("soft", "hard", "none").
        flicker_enabled: Whether flicker effect is active.
        flicker_seed: RNG seed for deterministic flicker.
        flicker_speed: Flicker animation speed.
        flicker_amount: Flicker intensity.
    """

    light_type: str = "point"
    x: float = 0.0
    y: float = 0.0
    radius: float = 100.0
    color: tuple[int, int, int, int] = (255, 255, 255, 255)
    intensity: float = 1.0
    mode: str = "none"
    flicker_enabled: bool = False
    flicker_seed: int | None = None
    flicker_speed: float = 1.0
    flicker_amount: float = 0.0

    def digest(self) -> str:
        """Return a deterministic string digest of this light config."""
        return (
            f"{self.light_type}:{self.x:.3f},{self.y:.3f}:"
            f"r{self.radius:.3f}:c{self.color}:i{self.intensity:.3f}:"
            f"m{self.mode}:f{self.flicker_enabled}"
        )


@dataclass(slots=True, frozen=True)
class OccluderConfig:
    """Configuration for a shadow-casting occluder.

    This is a headless representation of an occluder that can be processed
    without GPU/Arcade dependencies. Used for deterministic planning.

    Attributes:
        occluder_id: Unique identifier for the occluder.
        occluder_type: Type of occluder ("rect", "poly").
        x: X position (for rect type).
        y: Y position (for rect type).
        width: Width in pixels (for rect type).
        height: Height in pixels (for rect type).
        points: List of (x, y) points (for poly type).
    """

    occluder_id: str = ""
    occluder_type: str = "rect"
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    points: tuple[tuple[float, float], ...] = ()

    def digest(self) -> str:
        """Return a deterministic string digest of this occluder config."""
        if self.occluder_type == "poly":
            pts_str = ";".join(f"{p[0]:.3f},{p[1]:.3f}" for p in self.points)
            return f"poly:{self.occluder_id}:{pts_str}"
        return (
            f"rect:{self.occluder_id}:"
            f"{self.x:.3f},{self.y:.3f},{self.width:.3f},{self.height:.3f}"
        )


@dataclass(slots=True)
class LightingSceneConfig:
    """Configuration for a complete lighting scene.

    Aggregates all lights, occluders, and global settings for a scene.
    This is the primary input to the lighting plan computation.

    Attributes:
        ambient_color: Base ambient color RGBA.
        ambient_tint: Optional tint applied to ambient.
        ambient_darkness_alpha: Darkness overlay alpha (0-255).
        lights: List of light configurations.
        occluders: List of occluder configurations.
        shadows_mode: Global shadow mode ("none", "hard", "soft").
        shadowmask_enabled: Whether shadow mask is enabled.
    """

    ambient_color: tuple[int, int, int, int] = DEFAULT_AMBIENT_COLOR
    ambient_tint: tuple[int, int, int, int] | None = None
    ambient_darkness_alpha: int = 0
    lights: list[LightConfig] = field(default_factory=list)
    occluders: list[OccluderConfig] = field(default_factory=list)
    shadows_mode: str = "none"
    shadowmask_enabled: bool = False

    def lights_digest(self) -> str:
        """Return a deterministic digest of all light configs."""
        digests = sorted(light.digest() for light in self.lights)
        return "|".join(digests)

    def occluders_digest(self) -> str:
        """Return a deterministic digest of all occluder configs."""
        digests = sorted(occ.digest() for occ in self.occluders)
        return "|".join(digests)


def normalize_color(
    color: tuple[int, ...] | list[int] | None,
    default: tuple[int, int, int, int] = (255, 255, 255, 255),
) -> tuple[int, int, int, int]:
    """Normalize a color value to RGBA tuple.

    Args:
        color: Input color as RGB or RGBA tuple/list, or None.
        default: Default color if input is None or invalid.

    Returns:
        RGBA tuple with values clamped to 0-255.
    """
    if color is None:
        return default

    if not isinstance(color, (tuple, list)):
        return default

    if len(color) < 3:
        return default

    r = max(0, min(255, int(color[0])))
    g = max(0, min(255, int(color[1])))
    b = max(0, min(255, int(color[2])))
    a = max(0, min(255, int(color[3]))) if len(color) > 3 else 255

    return (r, g, b, a)


def parse_light_config(data: dict[str, Any]) -> LightConfig:
    """Parse a light configuration from a dictionary.

    Args:
        data: Dictionary with light configuration fields.

    Returns:
        LightConfig instance.
    """
    color_raw = data.get("color", (255, 255, 255, 255))
    color = normalize_color(color_raw)

    return LightConfig(
        light_type=str(data.get("type", "point")),
        x=float(data.get("x", 0.0)),
        y=float(data.get("y", 0.0)),
        radius=float(data.get("radius", 100.0)),
        color=color,
        intensity=float(data.get("intensity", 1.0)),
        mode=str(data.get("mode", "none")),
        flicker_enabled=bool(data.get("flicker_enabled", False)),
        flicker_seed=data.get("flicker_seed"),
        flicker_speed=float(data.get("flicker_speed", 1.0)),
        flicker_amount=float(data.get("flicker_amount", 0.0)),
    )


def parse_occluder_config(data: dict[str, Any]) -> OccluderConfig:
    """Parse an occluder configuration from a dictionary.

    Args:
        data: Dictionary with occluder configuration fields.

    Returns:
        OccluderConfig instance.
    """
    occluder_type = str(data.get("type", "rect"))
    points_raw = data.get("points", [])
    points = tuple((float(p[0]), float(p[1])) for p in points_raw) if points_raw else ()

    return OccluderConfig(
        occluder_id=str(data.get("id", data.get("name", ""))),
        occluder_type=occluder_type,
        x=float(data.get("x", 0.0)),
        y=float(data.get("y", 0.0)),
        width=float(data.get("width", 0.0)),
        height=float(data.get("height", 0.0)),
        points=points,
    )


def parse_scene_config(
    lights_data: list[dict[str, Any]] | None = None,
    occluders_data: list[dict[str, Any]] | None = None,
    ambient_color: tuple[int, ...] | list[int] | None = None,
    shadows_mode: str = "none",
) -> LightingSceneConfig:
    """Parse a complete lighting scene configuration.

    Args:
        lights_data: List of light config dictionaries.
        occluders_data: List of occluder config dictionaries.
        ambient_color: Ambient color as RGB or RGBA.
        shadows_mode: Shadow mode string.

    Returns:
        LightingSceneConfig instance.
    """
    lights = [parse_light_config(ld) for ld in (lights_data or [])]
    occluders = [parse_occluder_config(od) for od in (occluders_data or [])]

    return LightingSceneConfig(
        ambient_color=normalize_color(ambient_color, DEFAULT_AMBIENT_COLOR),
        lights=lights,
        occluders=occluders,
        shadows_mode=shadows_mode,
    )
