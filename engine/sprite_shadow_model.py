"""Pure model for sprite drop shadows (HD-2D blob shadows).

Computes shadow parameters deterministically based on render_layer and depth_z.
Designed for headless-safe + deterministic rendering.

Shadow convention:
- Shadows draw BEFORE sprites in the render pass
- Deeper entities (lower render_layer / depth_z) get smaller, lighter shadows
- Nearer entities (higher render_layer / depth_z) get larger, darker shadows

Multi-layer shadow system (drawn in order):
1. AO shadow (optional): Large, very low alpha, ambient occlusion halo
2. Base shadow: Standard blob shadow
3. Contact shadow: Smaller, darker, closer to feet for grounding
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple


@dataclass(frozen=True, slots=True)
class ShadowParams:
    """Computed shadow parameters for a sprite."""

    scale: float
    alpha: float
    offset_y: float

    def to_dict(self) -> Dict[str, float]:
        """Convert to dict for serialization/testing."""
        return {
            "scale": self.scale,
            "alpha": self.alpha,
            "offset_y": self.offset_y,
        }


@dataclass(frozen=True, slots=True)
class ContactShadowParams:
    """Computed contact shadow parameters (smaller, darker, closer to feet)."""

    scale: float
    alpha: float
    offset_y: float

    def to_dict(self) -> Dict[str, float]:
        """Convert to dict for serialization/testing."""
        return {
            "scale": self.scale,
            "alpha": self.alpha,
            "offset_y": self.offset_y,
        }


@dataclass(frozen=True, slots=True)
class AoShadowParams:
    """Computed AO (ambient occlusion) shadow parameters (larger, very low alpha)."""

    scale: float
    alpha: float
    offset_y: float

    def to_dict(self) -> Dict[str, float]:
        """Convert to dict for serialization/testing."""
        return {
            "scale": self.scale,
            "alpha": self.alpha,
            "offset_y": self.offset_y,
        }


@dataclass(frozen=True, slots=True)
class ShadowEllipse:
    """Computed shadow ellipse geometry."""

    cx: float
    cy: float
    width: float
    height: float

    def to_tuple(self) -> Tuple[float, float, float, float]:
        """Return (cx, cy, width, height) tuple."""
        return (self.cx, self.cy, self.width, self.height)


# -----------------------------------------------------------------------------
# Constants for depth-based shadow scaling
# -----------------------------------------------------------------------------

# Base shadow dimensions (ellipse half-widths at scale=1.0)
DEFAULT_SHADOW_WIDTH = 24.0
DEFAULT_SHADOW_HEIGHT = 8.0

# Depth influence on shadow parameters
# These are tuned for typical HD-2D games with render_layer in [-10, 10] range
# and depth_z in [-100, 100] range

# How much render_layer affects shadow (per unit of render_layer)
RENDER_LAYER_SCALE_FACTOR = 0.02  # +2% scale per render_layer
RENDER_LAYER_ALPHA_FACTOR = 0.01  # +1% alpha per render_layer
RENDER_LAYER_OFFSET_FACTOR = 0.5  # +0.5px offset_y per render_layer

# How much depth_z affects shadow (per unit of depth_z)
DEPTH_Z_SCALE_FACTOR = 0.001  # +0.1% scale per depth_z
DEPTH_Z_ALPHA_FACTOR = 0.0005  # +0.05% alpha per depth_z
DEPTH_Z_OFFSET_FACTOR = 0.05  # +0.05px offset_y per depth_z

# Clamp ranges
MIN_SCALE = 0.3
MAX_SCALE = 2.0
MIN_ALPHA = 0.1
MAX_ALPHA = 0.6
MIN_OFFSET_Y = -20.0
MAX_OFFSET_Y = 10.0


def compute_shadow_params(
    render_layer: int,
    depth_z: float,
    *,
    base_scale: float = 1.0,
    base_alpha: float = 0.35,
    base_offset_y: float = -4.0,
) -> ShadowParams:
    """Compute shadow parameters based on entity depth.

    Args:
        render_layer: Entity's render layer (int, lower = further back)
        depth_z: Entity's fine depth value (float, lower = further back)
        base_scale: Base shadow scale multiplier (default 1.0)
        base_alpha: Base shadow alpha (default 0.35)
        base_offset_y: Base y offset from sprite center (default -4.0, below sprite)

    Returns:
        ShadowParams with computed scale, alpha, offset_y

    The algorithm:
    - Higher render_layer / depth_z = nearer = larger + darker shadow
    - Lower render_layer / depth_z = farther = smaller + lighter shadow
    """
    # Compute depth influence
    layer_influence = float(render_layer) * RENDER_LAYER_SCALE_FACTOR
    depth_influence = float(depth_z) * DEPTH_Z_SCALE_FACTOR

    # Scale: nearer = larger shadow
    scale = base_scale * (1.0 + layer_influence + depth_influence)
    scale = max(MIN_SCALE, min(MAX_SCALE, scale))

    # Alpha: nearer = darker shadow
    alpha_layer = float(render_layer) * RENDER_LAYER_ALPHA_FACTOR
    alpha_depth = float(depth_z) * DEPTH_Z_ALPHA_FACTOR
    alpha = base_alpha * (1.0 + alpha_layer + alpha_depth)
    alpha = max(MIN_ALPHA, min(MAX_ALPHA, alpha))

    # Offset Y: nearer = lower offset (shadow closer to sprite)
    offset_layer = float(render_layer) * RENDER_LAYER_OFFSET_FACTOR
    offset_depth = float(depth_z) * DEPTH_Z_OFFSET_FACTOR
    offset_y = base_offset_y - (offset_layer + offset_depth)
    offset_y = max(MIN_OFFSET_Y, min(MAX_OFFSET_Y, offset_y))

    return ShadowParams(
        scale=round(scale, 6),
        alpha=round(alpha, 6),
        offset_y=round(offset_y, 6),
    )


def compute_shadow_ellipse(
    sprite_x: float,
    sprite_y: float,
    params: ShadowParams,
    *,
    base_width: float = DEFAULT_SHADOW_WIDTH,
    base_height: float = DEFAULT_SHADOW_HEIGHT,
) -> ShadowEllipse:
    """Compute shadow ellipse geometry.

    Args:
        sprite_x: Sprite center x position
        sprite_y: Sprite center y position
        params: Shadow parameters from compute_shadow_params
        base_width: Base ellipse width (default 24.0)
        base_height: Base ellipse height (default 8.0)

    Returns:
        ShadowEllipse with (cx, cy, width, height)
    """
    # Shadow center is offset below sprite
    cx = float(sprite_x)
    cy = float(sprite_y) + params.offset_y

    # Apply scale to dimensions
    width = base_width * params.scale
    height = base_height * params.scale

    return ShadowEllipse(
        cx=round(cx, 6),
        cy=round(cy, 6),
        width=round(width, 6),
        height=round(height, 6),
    )


# -----------------------------------------------------------------------------
# Contact Shadow (smaller, darker, closer to feet)
# -----------------------------------------------------------------------------

# Default contact shadow multipliers
DEFAULT_CONTACT_SCALE = 0.55  # 55% of base size
DEFAULT_CONTACT_ALPHA_MUL = 1.35  # 35% darker than base
DEFAULT_CONTACT_OFFSET_Y_ADD = 2.0  # Slightly higher (closer to feet)


def compute_contact_shadow_params(
    base_params: ShadowParams,
    *,
    contact_scale: float = DEFAULT_CONTACT_SCALE,
    contact_alpha_mul: float = DEFAULT_CONTACT_ALPHA_MUL,
    contact_offset_y_add: float = DEFAULT_CONTACT_OFFSET_Y_ADD,
) -> ContactShadowParams:
    """Compute contact shadow parameters from base shadow params.

    Contact shadows are smaller, darker ellipses closer to the sprite's feet
    to enhance grounding.

    Args:
        base_params: Base shadow parameters
        contact_scale: Scale multiplier relative to base (default 0.55)
        contact_alpha_mul: Alpha multiplier relative to base (default 1.35)
        contact_offset_y_add: Y offset added to base offset (default 2.0, closer to feet)

    Returns:
        ContactShadowParams with computed values
    """
    # Scale is smaller than base
    scale = base_params.scale * contact_scale
    scale = max(MIN_SCALE * 0.5, min(MAX_SCALE, scale))  # Allow smaller minimum

    # Alpha is higher (darker) but clamped to 1.0
    alpha = base_params.alpha * contact_alpha_mul
    alpha = max(0.0, min(1.0, alpha))

    # Offset is closer to sprite feet (less negative / more positive)
    offset_y = base_params.offset_y + contact_offset_y_add
    offset_y = max(MIN_OFFSET_Y, min(MAX_OFFSET_Y, offset_y))

    return ContactShadowParams(
        scale=round(scale, 6),
        alpha=round(alpha, 6),
        offset_y=round(offset_y, 6),
    )


def compute_contact_shadow_ellipse(
    sprite_x: float,
    sprite_y: float,
    params: ContactShadowParams,
    *,
    base_width: float = DEFAULT_SHADOW_WIDTH,
    base_height: float = DEFAULT_SHADOW_HEIGHT,
) -> ShadowEllipse:
    """Compute contact shadow ellipse geometry.

    Args:
        sprite_x: Sprite center x position
        sprite_y: Sprite center y position
        params: Contact shadow parameters
        base_width: Base ellipse width (default 24.0)
        base_height: Base ellipse height (default 8.0)

    Returns:
        ShadowEllipse with (cx, cy, width, height)
    """
    cx = float(sprite_x)
    cy = float(sprite_y) + params.offset_y
    width = base_width * params.scale
    height = base_height * params.scale

    return ShadowEllipse(
        cx=round(cx, 6),
        cy=round(cy, 6),
        width=round(width, 6),
        height=round(height, 6),
    )


# -----------------------------------------------------------------------------
# AO Shadow (larger, very low alpha ambient occlusion halo)
# -----------------------------------------------------------------------------

# Default AO shadow multipliers
DEFAULT_AO_SCALE = 1.25  # 125% of base size
DEFAULT_AO_ALPHA_MUL = 0.35  # Much lighter than base
DEFAULT_AO_OFFSET_Y_ADD = -1.0  # Slightly lower (behind base shadow)


def compute_ao_shadow_params(
    base_params: ShadowParams,
    *,
    ao_scale: float = DEFAULT_AO_SCALE,
    ao_alpha_mul: float = DEFAULT_AO_ALPHA_MUL,
    ao_offset_y_add: float = DEFAULT_AO_OFFSET_Y_ADD,
) -> AoShadowParams:
    """Compute AO (ambient occlusion) shadow parameters from base shadow params.

    AO shadows are larger, very low alpha ellipses that create a subtle halo
    around the base shadow for enhanced grounding.

    Args:
        base_params: Base shadow parameters
        ao_scale: Scale multiplier relative to base (default 1.25)
        ao_alpha_mul: Alpha multiplier relative to base (default 0.35)
        ao_offset_y_add: Y offset added to base offset (default -1.0)

    Returns:
        AoShadowParams with computed values
    """
    # Scale is larger than base
    scale = base_params.scale * ao_scale
    scale = max(MIN_SCALE, min(MAX_SCALE * 1.5, scale))  # Allow larger maximum

    # Alpha is much lower (subtler)
    alpha = base_params.alpha * ao_alpha_mul
    alpha = max(0.0, min(0.5, alpha))  # Cap at 0.5 to keep it subtle

    # Offset is slightly lower (behind base shadow)
    offset_y = base_params.offset_y + ao_offset_y_add
    offset_y = max(MIN_OFFSET_Y, min(MAX_OFFSET_Y, offset_y))

    return AoShadowParams(
        scale=round(scale, 6),
        alpha=round(alpha, 6),
        offset_y=round(offset_y, 6),
    )


def compute_ao_shadow_ellipse(
    sprite_x: float,
    sprite_y: float,
    params: AoShadowParams,
    *,
    base_width: float = DEFAULT_SHADOW_WIDTH,
    base_height: float = DEFAULT_SHADOW_HEIGHT,
) -> ShadowEllipse:
    """Compute AO shadow ellipse geometry.

    Args:
        sprite_x: Sprite center x position
        sprite_y: Sprite center y position
        params: AO shadow parameters
        base_width: Base ellipse width (default 24.0)
        base_height: Base ellipse height (default 8.0)

    Returns:
        ShadowEllipse with (cx, cy, width, height)
    """
    cx = float(sprite_x)
    cy = float(sprite_y) + params.offset_y
    width = base_width * params.scale
    height = base_height * params.scale

    return ShadowEllipse(
        cx=round(cx, 6),
        cy=round(cy, 6),
        width=round(width, 6),
        height=round(height, 6),
    )


def should_draw_shadow(
    entity_data: Dict[str, Any] | None,
    *,
    default_enabled: bool = True,
) -> bool:
    """Determine if shadow should be drawn for an entity.

    Args:
        entity_data: Entity dict with optional shadow_enabled field
        default_enabled: Default value if shadow_enabled not specified

    Returns:
        True if shadow should be drawn
    """
    if entity_data is None:
        return default_enabled

    # Check explicit shadow_enabled flag
    shadow_enabled = entity_data.get("shadow_enabled")
    if shadow_enabled is not None:
        return bool(shadow_enabled)

    return default_enabled


def should_draw_contact_shadow(
    entity_data: Dict[str, Any] | None,
    *,
    default_enabled: bool = True,
) -> bool:
    """Determine if contact shadow should be drawn for an entity.

    Args:
        entity_data: Entity dict with optional shadow_contact_enabled field
        default_enabled: Default value if shadow_contact_enabled not specified

    Returns:
        True if contact shadow should be drawn
    """
    if entity_data is None:
        return default_enabled

    # Check explicit shadow_contact_enabled flag
    contact_enabled = entity_data.get("shadow_contact_enabled")
    if contact_enabled is not None:
        return bool(contact_enabled)

    return default_enabled


def should_draw_ao_shadow(
    entity_data: Dict[str, Any] | None,
    *,
    default_enabled: bool = False,
) -> bool:
    """Determine if AO shadow should be drawn for an entity.

    Args:
        entity_data: Entity dict with optional shadow_ao_enabled field
        default_enabled: Default value if shadow_ao_enabled not specified

    Returns:
        True if AO shadow should be drawn
    """
    if entity_data is None:
        return default_enabled

    # Check explicit shadow_ao_enabled flag
    ao_enabled = entity_data.get("shadow_ao_enabled")
    if ao_enabled is not None:
        return bool(ao_enabled)

    return default_enabled


def get_shadow_overrides(
    entity_data: Dict[str, Any] | None,
) -> Dict[str, float]:
    """Extract per-entity shadow overrides.

    Args:
        entity_data: Entity dict with optional shadow_* fields

    Returns:
        Dict with override values (only includes fields that are set)
    """
    overrides: Dict[str, float] = {}
    if entity_data is None:
        return overrides

    # shadow_scale: multiplier for base scale
    if "shadow_scale" in entity_data:
        try:
            overrides["scale_mult"] = float(entity_data["shadow_scale"])
        except (TypeError, ValueError):
            pass

    # shadow_alpha: override alpha (0..1)
    if "shadow_alpha" in entity_data:
        try:
            alpha = float(entity_data["shadow_alpha"])
            overrides["alpha"] = max(0.0, min(1.0, alpha))
        except (TypeError, ValueError):
            pass

    # shadow_offset_y: override y offset
    if "shadow_offset_y" in entity_data:
        try:
            overrides["offset_y"] = float(entity_data["shadow_offset_y"])
        except (TypeError, ValueError):
            pass

    # shadow_contact_scale: multiplier for contact shadow scale
    if "shadow_contact_scale" in entity_data:
        try:
            overrides["contact_scale"] = float(entity_data["shadow_contact_scale"])
        except (TypeError, ValueError):
            pass

    # shadow_contact_alpha: override contact shadow alpha (0..1)
    if "shadow_contact_alpha" in entity_data:
        try:
            alpha = float(entity_data["shadow_contact_alpha"])
            overrides["contact_alpha"] = max(0.0, min(1.0, alpha))
        except (TypeError, ValueError):
            pass

    return overrides


def compute_shadow_params_with_overrides(
    render_layer: int,
    depth_z: float,
    entity_data: Dict[str, Any] | None,
    *,
    base_scale: float = 1.0,
    base_alpha: float = 0.35,
    base_offset_y: float = -4.0,
) -> ShadowParams:
    """Compute shadow params with per-entity overrides applied.

    Args:
        render_layer: Entity's render layer
        depth_z: Entity's fine depth value
        entity_data: Entity dict with optional shadow_* overrides
        base_scale: Base shadow scale
        base_alpha: Base shadow alpha
        base_offset_y: Base y offset

    Returns:
        ShadowParams with overrides applied
    """
    # Get base params
    params = compute_shadow_params(
        render_layer,
        depth_z,
        base_scale=base_scale,
        base_alpha=base_alpha,
        base_offset_y=base_offset_y,
    )

    # Apply overrides
    overrides = get_shadow_overrides(entity_data)
    if not overrides:
        return params

    scale = params.scale
    alpha = params.alpha
    offset_y = params.offset_y

    # Scale multiplier
    if "scale_mult" in overrides:
        scale = scale * overrides["scale_mult"]
        scale = max(MIN_SCALE, min(MAX_SCALE, scale))

    # Alpha override (direct replacement, not multiplier)
    if "alpha" in overrides:
        alpha = overrides["alpha"]

    # Offset Y override (direct replacement)
    if "offset_y" in overrides:
        offset_y = overrides["offset_y"]

    return ShadowParams(
        scale=round(scale, 6),
        alpha=round(alpha, 6),
        offset_y=round(offset_y, 6),
    )


# -----------------------------------------------------------------------------
# Sprite helper for runtime integration
# -----------------------------------------------------------------------------


def compute_sprite_shadow(
    sprite: Any,
    *,
    base_scale: float = 1.0,
    base_alpha: float = 0.35,
    base_offset_y: float = -4.0,
    base_width: float = DEFAULT_SHADOW_WIDTH,
    base_height: float = DEFAULT_SHADOW_HEIGHT,
) -> Tuple[ShadowEllipse, float] | None:
    """Compute shadow ellipse for a sprite.

    Args:
        sprite: Arcade sprite with mesh_entity_data attribute
        base_scale: Base shadow scale
        base_alpha: Base shadow alpha
        base_offset_y: Base y offset
        base_width: Base ellipse width
        base_height: Base ellipse height

    Returns:
        Tuple of (ShadowEllipse, alpha) or None if shadow disabled
    """
    entity_data = getattr(sprite, "mesh_entity_data", None) or {}

    # Check if shadow enabled
    if not should_draw_shadow(entity_data):
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

    # Compute params with overrides
    params = compute_shadow_params_with_overrides(
        render_layer,
        depth_z,
        entity_data,
        base_scale=base_scale,
        base_alpha=base_alpha,
        base_offset_y=base_offset_y,
    )

    # Get sprite position
    sprite_x = float(getattr(sprite, "center_x", 0.0))
    sprite_y = float(getattr(sprite, "center_y", 0.0))

    # Compute ellipse
    ellipse = compute_shadow_ellipse(
        sprite_x,
        sprite_y,
        params,
        base_width=base_width,
        base_height=base_height,
    )

    return (ellipse, params.alpha)


@dataclass(frozen=True, slots=True)
class MultiLayerShadow:
    """Multi-layer shadow data for a sprite.

    Contains base shadow plus optional contact and AO shadow layers.
    Shadows should be drawn in order: AO -> base -> contact
    """

    base_ellipse: ShadowEllipse
    base_alpha: float
    contact_ellipse: ShadowEllipse | None
    contact_alpha: float
    ao_ellipse: ShadowEllipse | None
    ao_alpha: float


def compute_sprite_multi_shadow(
    sprite: Any,
    *,
    base_scale: float = 1.0,
    base_alpha: float = 0.35,
    base_offset_y: float = -4.0,
    base_width: float = DEFAULT_SHADOW_WIDTH,
    base_height: float = DEFAULT_SHADOW_HEIGHT,
    contact_enabled: bool = True,
    ao_enabled: bool = False,
) -> MultiLayerShadow | None:
    """Compute multi-layer shadow data for a sprite.

    Returns shadow ellipses for base, contact, and AO layers.
    Respects per-entity overrides for each layer.

    Args:
        sprite: Arcade sprite with mesh_entity_data attribute
        base_scale: Base shadow scale
        base_alpha: Base shadow alpha
        base_offset_y: Base y offset
        base_width: Base ellipse width
        base_height: Base ellipse height
        contact_enabled: Scene-level contact shadow enable (default True)
        ao_enabled: Scene-level AO shadow enable (default False)

    Returns:
        MultiLayerShadow with all layer data, or None if base shadow disabled
    """
    entity_data = getattr(sprite, "mesh_entity_data", None) or {}

    # Check if base shadow enabled
    if not should_draw_shadow(entity_data):
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

    # Compute base params with overrides
    base_params = compute_shadow_params_with_overrides(
        render_layer,
        depth_z,
        entity_data,
        base_scale=base_scale,
        base_alpha=base_alpha,
        base_offset_y=base_offset_y,
    )

    # Get sprite position
    sprite_x = float(getattr(sprite, "center_x", 0.0))
    sprite_y = float(getattr(sprite, "center_y", 0.0))

    # Compute base ellipse
    base_ellipse = compute_shadow_ellipse(
        sprite_x,
        sprite_y,
        base_params,
        base_width=base_width,
        base_height=base_height,
    )

    # Get overrides for contact/AO
    overrides = get_shadow_overrides(entity_data)

    # Contact shadow - entity can override scene setting
    contact_ellipse: ShadowEllipse | None = None
    contact_alpha_val = 0.0

    # Check if contact shadow should draw: entity override takes precedence, else use scene setting
    draw_contact = should_draw_contact_shadow(entity_data, default_enabled=contact_enabled)

    if draw_contact:
        contact_scale_override = overrides.get("contact_scale", DEFAULT_CONTACT_SCALE)
        contact_alpha_override = overrides.get("contact_alpha")

        contact_params = compute_contact_shadow_params(
            base_params,
            contact_scale=contact_scale_override,
        )

        # Apply alpha override if specified
        if contact_alpha_override is not None:
            contact_alpha_val = contact_alpha_override
        else:
            contact_alpha_val = contact_params.alpha

        contact_ellipse = compute_contact_shadow_ellipse(
            sprite_x,
            sprite_y,
            contact_params,
            base_width=base_width,
            base_height=base_height,
        )

    # AO shadow - entity can override scene setting
    ao_ellipse: ShadowEllipse | None = None
    ao_alpha_val = 0.0

    # Check if AO shadow should draw: entity override takes precedence, else use scene setting
    draw_ao = should_draw_ao_shadow(entity_data, default_enabled=ao_enabled)

    if draw_ao:
        ao_params = compute_ao_shadow_params(base_params)
        ao_alpha_val = ao_params.alpha

        ao_ellipse = compute_ao_shadow_ellipse(
            sprite_x,
            sprite_y,
            ao_params,
            base_width=base_width,
            base_height=base_height,
        )

    return MultiLayerShadow(
        base_ellipse=base_ellipse,
        base_alpha=base_params.alpha,
        contact_ellipse=contact_ellipse,
        contact_alpha=contact_alpha_val,
        ao_ellipse=ao_ellipse,
        ao_alpha=ao_alpha_val,
    )

