"""Pure model for depth-based sprite tinting (HD-2D atmospheric depth).

Computes tint colors deterministically based on render_layer and depth_z.
Designed for headless-safe + deterministic rendering.

Tint convention:
- Farther objects (lower render_layer / depth_z) get darker/desaturated
- Nearer objects (higher render_layer / depth_z) remain vivid/neutral
- Tinting is purely visual and does not affect sorting
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

# Type aliases for color tuples
ColorRGB = Tuple[int, int, int]
ColorRGBA = Tuple[int, int, int, int]
ColorType = ColorRGB | ColorRGBA


@dataclass(frozen=True, slots=True)
class DepthTintSettings:
    """Configuration for depth-based tinting."""

    enabled: bool = False
    near_color: ColorRGBA = (255, 255, 255, 255)  # Neutral (no tint) for near
    far_color: ColorRGBA = (180, 180, 200, 255)  # Slightly dark/blue for far
    strength: float = 0.35  # Blend factor (0 = no effect, 1 = full effect)
    layer_range: Tuple[int, int] = (-10, 10)  # Expected render_layer range
    depth_z_range: Tuple[float, float] = (-100.0, 100.0)  # Expected depth_z range

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "enabled": self.enabled,
            "near_color": list(self.near_color),
            "far_color": list(self.far_color),
            "strength": self.strength,
            "layer_range": list(self.layer_range),
            "depth_z_range": list(self.depth_z_range),
        }


# Default settings instance
DEFAULT_DEPTH_TINT_SETTINGS = DepthTintSettings()


# -----------------------------------------------------------------------------
# Core computation functions
# -----------------------------------------------------------------------------


def compute_depth_factor(
    render_layer: int,
    depth_z: float,
    *,
    sort_mode: str = "y_sort",
    layer_range: Tuple[int, int] = (-10, 10),
    depth_z_range: Tuple[float, float] = (-100.0, 100.0),
) -> float:
    """Compute normalized depth factor (0 = near, 1 = far).

    Args:
        render_layer: Entity's render layer (lower = farther back)
        depth_z: Entity's fine depth value (lower = farther back)
        sort_mode: 'y_sort' or 'explicit_z' - determines weighting
        layer_range: (min, max) expected render_layer range
        depth_z_range: (min, max) expected depth_z range

    Returns:
        Float in [0, 1] where 0 = near (high depth), 1 = far (low depth)
        Deterministic and monotonic.
    """
    # Normalize render_layer to [0, 1]
    layer_min, layer_max = layer_range
    layer_span = max(1, layer_max - layer_min)
    # Higher render_layer = nearer = lower factor
    layer_factor = 1.0 - (float(render_layer - layer_min) / layer_span)
    layer_factor = max(0.0, min(1.0, layer_factor))

    if sort_mode == "explicit_z":
        # In explicit_z mode, depth_z is the primary depth indicator
        # Combine layer and depth_z with more weight on depth_z
        z_min, z_max = depth_z_range
        z_span = max(1.0, z_max - z_min)
        # Higher depth_z = nearer = lower factor
        z_factor = 1.0 - (float(depth_z - z_min) / z_span)
        z_factor = max(0.0, min(1.0, z_factor))

        # Weight: 30% layer, 70% depth_z in explicit_z mode
        combined = 0.3 * layer_factor + 0.7 * z_factor
    else:
        # y_sort mode: only use render_layer
        combined = layer_factor

    return round(max(0.0, min(1.0, combined)), 6)


def lerp_color(
    c0: ColorType,
    c1: ColorType,
    t: float,
) -> ColorRGBA:
    """Linear interpolation between two colors.

    Args:
        c0: Start color (RGB or RGBA)
        c1: End color (RGB or RGBA)
        t: Interpolation factor (0 = c0, 1 = c1)

    Returns:
        Interpolated RGBA color tuple with values clamped to [0, 255].
    """
    t = max(0.0, min(1.0, t))

    # Normalize to RGBA
    r0, g0, b0 = c0[0], c0[1], c0[2]
    a0 = c0[3] if len(c0) >= 4 else 255
    r1, g1, b1 = c1[0], c1[1], c1[2]
    a1 = c1[3] if len(c1) >= 4 else 255

    # Lerp each channel
    r = int(round(r0 + (r1 - r0) * t))
    g = int(round(g0 + (g1 - g0) * t))
    b = int(round(b0 + (b1 - b0) * t))
    a = int(round(a0 + (a1 - a0) * t))

    # Clamp to valid range
    return (
        max(0, min(255, r)),
        max(0, min(255, g)),
        max(0, min(255, b)),
        max(0, min(255, a)),
    )


def compute_tint_rgba(
    render_layer: int,
    depth_z: float,
    settings: DepthTintSettings | None = None,
    *,
    sort_mode: str = "y_sort",
) -> ColorRGBA:
    """Compute tint color for a sprite based on depth.

    Args:
        render_layer: Entity's render layer
        depth_z: Entity's fine depth value
        settings: Tint settings (uses defaults if None)
        sort_mode: 'y_sort' or 'explicit_z'

    Returns:
        RGBA tint color tuple (255, 255, 255, 255 = no tint).
    """
    if settings is None:
        settings = DEFAULT_DEPTH_TINT_SETTINGS

    if not settings.enabled:
        return (255, 255, 255, 255)  # Neutral, no effect

    # Get depth factor (0 = near, 1 = far)
    depth_factor = compute_depth_factor(
        render_layer,
        depth_z,
        sort_mode=sort_mode,
        layer_range=settings.layer_range,
        depth_z_range=settings.depth_z_range,
    )

    # Interpolate between near and far colors
    base_tint = lerp_color(settings.near_color, settings.far_color, depth_factor)

    # Apply strength (blend between neutral and computed tint)
    neutral = (255, 255, 255, 255)
    final_tint = lerp_color(neutral, base_tint, settings.strength)

    return final_tint


def apply_tint_to_color(
    base_rgba: ColorType,
    tint_rgba: ColorType,
) -> ColorRGBA:
    """Apply tint to a base color using multiplicative blending.

    Args:
        base_rgba: Original sprite color (RGB or RGBA)
        tint_rgba: Tint color to apply (RGB or RGBA)

    Returns:
        Final RGBA color after tint application.
    """
    # Normalize to RGBA
    br, bg, bb = base_rgba[0], base_rgba[1], base_rgba[2]
    ba = base_rgba[3] if len(base_rgba) >= 4 else 255
    tr, tg, tb = tint_rgba[0], tint_rgba[1], tint_rgba[2]
    ta = tint_rgba[3] if len(tint_rgba) >= 4 else 255

    # Multiplicative blend (normalized to 255)
    r = int(round(br * tr / 255.0))
    g = int(round(bg * tg / 255.0))
    b = int(round(bb * tb / 255.0))
    a = int(round(ba * ta / 255.0))

    return (
        max(0, min(255, r)),
        max(0, min(255, g)),
        max(0, min(255, b)),
        max(0, min(255, a)),
    )


# -----------------------------------------------------------------------------
# Scene settings parsing
# -----------------------------------------------------------------------------


def parse_depth_tint_settings(
    scene_settings: Dict[str, Any] | None,
) -> DepthTintSettings:
    """Parse depth tint settings from scene settings dict.

    Args:
        scene_settings: Scene settings dict with optional depth_tint_* fields

    Returns:
        DepthTintSettings instance
    """
    if scene_settings is None:
        return DEFAULT_DEPTH_TINT_SETTINGS

    enabled = bool(scene_settings.get("depth_tint_enabled", False))
    if not enabled:
        return DepthTintSettings(enabled=False)

    # Parse near color
    near_color = DEFAULT_DEPTH_TINT_SETTINGS.near_color
    raw_near = scene_settings.get("depth_tint_near_color")
    if isinstance(raw_near, (list, tuple)) and len(raw_near) >= 3:
        try:
            r = max(0, min(255, int(raw_near[0])))
            g = max(0, min(255, int(raw_near[1])))
            b = max(0, min(255, int(raw_near[2])))
            a = max(0, min(255, int(raw_near[3]))) if len(raw_near) >= 4 else 255
            near_color = (r, g, b, a)
        except (TypeError, ValueError):
            pass

    # Parse far color
    far_color = DEFAULT_DEPTH_TINT_SETTINGS.far_color
    raw_far = scene_settings.get("depth_tint_far_color")
    if isinstance(raw_far, (list, tuple)) and len(raw_far) >= 3:
        try:
            r = max(0, min(255, int(raw_far[0])))
            g = max(0, min(255, int(raw_far[1])))
            b = max(0, min(255, int(raw_far[2])))
            a = max(0, min(255, int(raw_far[3]))) if len(raw_far) >= 4 else 255
            far_color = (r, g, b, a)
        except (TypeError, ValueError):
            pass

    # Parse strength
    strength = DEFAULT_DEPTH_TINT_SETTINGS.strength
    raw_strength = scene_settings.get("depth_tint_strength")
    if raw_strength is not None:
        try:
            strength = max(0.0, min(1.0, float(raw_strength)))
        except (TypeError, ValueError):
            pass

    # Parse layer range
    layer_range = DEFAULT_DEPTH_TINT_SETTINGS.layer_range
    raw_layer_range = scene_settings.get("depth_tint_layer_range")
    if isinstance(raw_layer_range, (list, tuple)) and len(raw_layer_range) >= 2:
        try:
            layer_range = (int(raw_layer_range[0]), int(raw_layer_range[1]))
        except (TypeError, ValueError):
            pass

    # Parse depth_z range
    depth_z_range = DEFAULT_DEPTH_TINT_SETTINGS.depth_z_range
    raw_z_range = scene_settings.get("depth_tint_z_range")
    if isinstance(raw_z_range, (list, tuple)) and len(raw_z_range) >= 2:
        try:
            depth_z_range = (float(raw_z_range[0]), float(raw_z_range[1]))
        except (TypeError, ValueError):
            pass

    return DepthTintSettings(
        enabled=True,
        near_color=near_color,
        far_color=far_color,
        strength=strength,
        layer_range=layer_range,
        depth_z_range=depth_z_range,
    )


# -----------------------------------------------------------------------------
# Entity-level helpers
# -----------------------------------------------------------------------------


def should_apply_depth_tint(
    entity_data: Dict[str, Any] | None,
    *,
    default_enabled: bool = True,
) -> bool:
    """Determine if depth tint should be applied to an entity.

    Args:
        entity_data: Entity dict with optional depth_tint_enabled field
        default_enabled: Default if entity has no override

    Returns:
        True if depth tint should be applied
    """
    if entity_data is None:
        return default_enabled

    override = entity_data.get("depth_tint_enabled")
    if override is not None:
        return bool(override)

    return default_enabled


def get_entity_tint_strength_override(
    entity_data: Dict[str, Any] | None,
) -> float | None:
    """Get per-entity tint strength override.

    Args:
        entity_data: Entity dict with optional depth_tint_strength field

    Returns:
        Override strength (0..1) or None if not set
    """
    if entity_data is None:
        return None

    raw = entity_data.get("depth_tint_strength")
    if raw is None:
        return None

    try:
        return max(0.0, min(1.0, float(raw)))
    except (TypeError, ValueError):
        return None


# -----------------------------------------------------------------------------
# Sprite-level helper for runtime integration
# -----------------------------------------------------------------------------


def compute_sprite_tint(
    sprite: Any,
    settings: DepthTintSettings,
    *,
    sort_mode: str = "y_sort",
) -> ColorRGBA | None:
    """Compute tint color for a sprite.

    Args:
        sprite: Arcade sprite with mesh_entity_data attribute
        settings: Depth tint settings from scene
        sort_mode: 'y_sort' or 'explicit_z'

    Returns:
        RGBA tint color or None if tinting disabled for this sprite
    """
    if not settings.enabled:
        return None

    entity_data = getattr(sprite, "mesh_entity_data", None) or {}

    # Check entity-level override
    if not should_apply_depth_tint(entity_data):
        return None

    # Get render depth values
    render_layer = 0
    depth_z = 0.0
    try:
        render_layer = int(entity_data.get("render_layer", 0))
    except (TypeError, ValueError):
        pass
    try:
        depth_z = float(entity_data.get("depth_z", 0.0))
    except (TypeError, ValueError):
        pass

    # Check for strength override
    strength_override = get_entity_tint_strength_override(entity_data)
    effective_settings = settings
    if strength_override is not None:
        effective_settings = DepthTintSettings(
            enabled=True,
            near_color=settings.near_color,
            far_color=settings.far_color,
            strength=strength_override,
            layer_range=settings.layer_range,
            depth_z_range=settings.depth_z_range,
        )

    return compute_tint_rgba(
        render_layer,
        depth_z,
        effective_settings,
        sort_mode=sort_mode,
    )


def apply_tint_to_sprite_color(
    sprite_color: ColorType | None,
    tint: ColorRGBA,
) -> ColorRGBA:
    """Apply tint to sprite's current color.

    Args:
        sprite_color: Sprite's current color (may be None or various formats)
        tint: Tint color to apply

    Returns:
        Final RGBA color
    """
    if sprite_color is None:
        # Default sprite color is white
        base = (255, 255, 255, 255)
    elif isinstance(sprite_color, (list, tuple)) and len(sprite_color) >= 3:
        r = int(sprite_color[0])
        g = int(sprite_color[1])
        b = int(sprite_color[2])
        a = int(sprite_color[3]) if len(sprite_color) >= 4 else 255
        base = (r, g, b, a)
    else:
        base = (255, 255, 255, 255)

    return apply_tint_to_color(base, tint)
