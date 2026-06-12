"""Lighting render helpers.

This module provides render-related utilities for the lighting system.
These functions wrap Arcade draw calls and layer operations, providing
a clean interface that can be mocked for testing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from engine.swallowed_exceptions import _log_swallow

if TYPE_CHECKING:
    from .lighting_config import LightConfig


@dataclass(slots=True)
class RenderStats:
    """Statistics from a render pass.

    Attributes:
        lights_drawn: Number of lights rendered.
        shadows_drawn: Number of shadow polygons rendered.
        layer_draws: Number of layer draw calls.
        mask_rendered: Whether shadow mask was rendered.
        fallback_used: Whether fallback rendering was used.
    """

    lights_drawn: int = 0
    shadows_drawn: int = 0
    layer_draws: int = 0
    mask_rendered: bool = False
    fallback_used: bool = False


def prepare_light_layer(
    layer: Any,
    ambient_color: tuple[int, int, int, int],
) -> bool:
    """Prepare a light layer for rendering.

    Sets up the layer with the ambient color. This is the setup
    phase before adding lights.

    Args:
        layer: Arcade LightLayer instance.
        ambient_color: RGBA ambient color.

    Returns:
        True if setup succeeded, False if layer is invalid.
    """
    if layer is None:
        return False

    try:
        # Set ambient color on layer if supported
        if hasattr(layer, "set_ambient_color"):
            layer.set_ambient_color(ambient_color)
        elif hasattr(layer, "ambient_color"):
            layer.ambient_color = ambient_color
        return True
    except Exception:  # noqa: BLE001  # REASON: LightLayer ambient-color adapters should fail closed when backend-specific setters reject the value
        _log_swallow("LGRT-001", "engine/lighting/lighting_render.py blanket swallow", once=True)
        return False


def draw_layer_safe(layer: Any) -> bool:
    """Draw a light layer safely.

    Wraps the layer draw call with error handling.

    Args:
        layer: Arcade LightLayer instance.

    Returns:
        True if draw succeeded, False if it failed.
    """
    if layer is None:
        return False

    try:
        if hasattr(layer, "draw"):
            layer.draw()
            return True
        return False
    except Exception:  # noqa: BLE001  # REASON: LightLayer draw failures should skip the lighting pass without aborting frame rendering
        _log_swallow("LGRT-002", "engine/lighting/lighting_render.py blanket swallow", once=True)
        return False


def clear_layer(layer: Any) -> bool:
    """Clear a light layer.

    Removes all lights from the layer.

    Args:
        layer: Arcade LightLayer instance.

    Returns:
        True if clear succeeded.
    """
    if layer is None:
        return False

    try:
        # Try different clear methods
        if hasattr(layer, "clear"):
            layer.clear()
            return True
        # Some versions use remove with iteration
        if hasattr(layer, "__iter__") and hasattr(layer, "remove"):
            for light in list(layer):
                layer.remove(light)
            return True
        return False
    except Exception:  # noqa: BLE001  # REASON: LightLayer clear failures should leave the existing layer state intact without aborting lighting updates
        _log_swallow("LGRT-003", "engine/lighting/lighting_render.py blanket swallow", once=True)
        return False


def add_light_to_layer(layer: Any, light: Any) -> bool:
    """Add a light to a layer.

    Args:
        layer: Arcade LightLayer instance.
        light: Arcade Light instance.

    Returns:
        True if add succeeded.
    """
    if layer is None or light is None:
        return False

    try:
        if hasattr(layer, "add"):
            layer.add(light)
            return True
        return False
    except Exception:  # noqa: BLE001  # REASON: LightLayer add failures should skip the individual light without aborting lighting updates
        _log_swallow("LGRT-004", "engine/lighting/lighting_render.py blanket swallow", once=True)
        return False


def remove_light_from_layer(layer: Any, light: Any) -> bool:
    """Remove a light from a layer.

    Args:
        layer: Arcade LightLayer instance.
        light: Arcade Light instance.

    Returns:
        True if remove succeeded.
    """
    if layer is None or light is None:
        return False

    try:
        if hasattr(layer, "remove"):
            layer.remove(light)
            return True
        return False
    except Exception:  # noqa: BLE001  # REASON: LightLayer remove failures should skip the individual light without aborting lighting updates
        _log_swallow("LGRT-005", "engine/lighting/lighting_render.py blanket swallow", once=True)
        return False


def use_layer_context(layer: Any) -> Any:
    """Get a context manager for using a light layer.

    Returns a context manager that activates the layer on enter
    and deactivates on exit.

    Args:
        layer: Arcade LightLayer instance.

    Returns:
        Context manager or None if layer is invalid.
    """
    if layer is None:
        return None

    if hasattr(layer, "use"):
        from .types import _LayerContext

        return _LayerContext(layer)

    return None


def compute_render_plan(
    lights: list["LightConfig"],
    shadows_enabled: bool,
    max_lights: int = 32,
) -> list[int]:
    """Compute which lights should be rendered.

    Determines rendering order and which lights to include based
    on limits and shadow requirements.

    Args:
        lights: Light configurations.
        shadows_enabled: Whether shadows are enabled.
        max_lights: Maximum lights to render.

    Returns:
        List of light indices in render order.
    """
    if not lights:
        return []

    # Separate ambient from point lights
    ambient_indices = []
    point_indices = []

    for i, light in enumerate(lights):
        if light.light_type == "ambient":
            ambient_indices.append(i)
        else:
            point_indices.append(i)

    # Ambient lights always first, then point lights
    result = ambient_indices + point_indices

    # Apply limit
    if len(result) > max_lights:
        result = result[:max_lights]

    return result
