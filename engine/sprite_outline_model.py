"""Pure model for faux sprite outlines (HD-2D rim light)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class OutlineSettings:
    """Scene-level outline settings."""

    enabled: bool = False
    color_rgba: tuple[int, int, int, int] = (0, 0, 0, 90)
    strength: float = 0.5
    radius_px: int = 1
    near_factor: float = 0.6


@dataclass(frozen=True, slots=True)
class OutlineDrawCall:
    x: float
    y: float
    color: tuple[int, int, int]
    alpha: int


DEFAULT_OUTLINE_SETTINGS = OutlineSettings()

# Depth influence on outline alpha
OUTLINE_LAYER_ALPHA_FACTOR = 0.02
OUTLINE_DEPTH_ALPHA_FACTOR = 0.001


def parse_outline_settings(scene_settings: dict[str, Any] | None) -> OutlineSettings:
    if not isinstance(scene_settings, dict):
        return DEFAULT_OUTLINE_SETTINGS
    enabled = bool(scene_settings.get("outline_enabled", False))
    if not enabled:
        return OutlineSettings(enabled=False)
    color = _coerce_rgba(scene_settings.get("outline_color_rgba")) or DEFAULT_OUTLINE_SETTINGS.color_rgba
    strength = _clamp_float(scene_settings.get("outline_strength", DEFAULT_OUTLINE_SETTINGS.strength), 0.0, 1.0)
    radius_px = _clamp_int(scene_settings.get("outline_radius_px", DEFAULT_OUTLINE_SETTINGS.radius_px), 0, 6)
    near_factor = _clamp_float(scene_settings.get("outline_near_factor", DEFAULT_OUTLINE_SETTINGS.near_factor), 0.0, 2.0)
    return OutlineSettings(
        enabled=True,
        color_rgba=color,
        strength=strength,
        radius_px=radius_px,
        near_factor=near_factor,
    )


def should_draw_outline(entity_data: dict[str, Any] | None, default_enabled: bool = False) -> bool:
    if not isinstance(entity_data, dict):
        return bool(default_enabled)
    if "outline_enabled" in entity_data:
        return bool(entity_data.get("outline_enabled"))
    return bool(default_enabled)


def get_outline_overrides(entity_data: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(entity_data, dict):
        return {}
    overrides: dict[str, Any] = {}
    if "outline_enabled" in entity_data:
        overrides["enabled"] = bool(entity_data.get("outline_enabled"))
    color = _coerce_rgba(entity_data.get("outline_color_rgba"))
    if color is not None:
        overrides["color_rgba"] = color
    if "outline_strength" in entity_data:
        overrides["strength"] = _clamp_float(entity_data.get("outline_strength"), 0.0, 1.0)
    if "outline_radius_px" in entity_data:
        overrides["radius_px"] = _clamp_int(entity_data.get("outline_radius_px"), 0, 6)
    return overrides


def apply_outline_overrides(base: OutlineSettings, overrides: dict[str, Any]) -> OutlineSettings:
    if not overrides:
        return base
    return OutlineSettings(
        enabled=bool(overrides.get("enabled", base.enabled)),
        color_rgba=overrides.get("color_rgba", base.color_rgba),
        strength=float(overrides.get("strength", base.strength)),
        radius_px=int(overrides.get("radius_px", base.radius_px)),
        near_factor=float(base.near_factor),
    )


def compute_outline_alpha(render_layer: int, depth_z: float, settings: OutlineSettings) -> int:
    if not settings.enabled:
        return 0
    base_alpha = int(settings.color_rgba[3]) if len(settings.color_rgba) >= 4 else 255
    strength = _clamp_float(settings.strength, 0.0, 1.0)
    depth_boost = (float(render_layer) * OUTLINE_LAYER_ALPHA_FACTOR) + (float(depth_z) * OUTLINE_DEPTH_ALPHA_FACTOR)
    depth_boost = max(-1.0, min(1.0, depth_boost))
    alpha = base_alpha * strength * (1.0 + depth_boost * settings.near_factor)
    alpha = max(0.0, min(255.0, alpha))
    return int(round(alpha))


def compute_outline_offsets(radius_px: int) -> list[tuple[int, int]]:
    radius = int(radius_px)
    if radius <= 0:
        return []
    r = radius
    return [
        (-r, 0),
        (r, 0),
        (0, -r),
        (0, r),
        (-r, -r),
        (-r, r),
        (r, -r),
        (r, r),
    ]


def compute_sprite_outline_draw_calls(
    sprite_x: float,
    sprite_y: float,
    render_layer: int,
    depth_z: float,
    settings: OutlineSettings,
    *,
    entity_data: dict[str, Any] | None = None,
) -> list[OutlineDrawCall]:
    if not should_draw_outline(entity_data, settings.enabled):
        return []
    overrides = get_outline_overrides(entity_data)
    effective = apply_outline_overrides(settings, overrides)
    if not effective.enabled:
        return []
    alpha = compute_outline_alpha(render_layer, depth_z, effective)
    if alpha <= 0:
        return []
    offsets = compute_outline_offsets(effective.radius_px)
    if not offsets:
        return []
    color = effective.color_rgba[:3]
    calls: list[OutlineDrawCall] = []
    for dx, dy in offsets:
        calls.append(
            OutlineDrawCall(
                x=round(float(sprite_x) + dx, 6),
                y=round(float(sprite_y) + dy, 6),
                color=(int(color[0]), int(color[1]), int(color[2])),
                alpha=int(alpha),
            )
        )
    return calls


def _coerce_rgba(value: Any) -> tuple[int, int, int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    try:
        r = max(0, min(255, int(value[0])))
        g = max(0, min(255, int(value[1])))
        b = max(0, min(255, int(value[2])))
        a = max(0, min(255, int(value[3]))) if len(value) >= 4 else 255
    except Exception:  # noqa: BLE001  # REASON: malformed RGBA outline colors should be rejected without breaking outline loading
        return None
    return (r, g, b, a)


def _clamp_float(value: Any, min_value: float, max_value: float) -> float:
    try:
        numeric = float(value)
    except Exception:  # noqa: BLE001  # REASON: invalid outline float inputs should fall back to the minimum outline scalar
        numeric = float(min_value)
    return max(min_value, min(max_value, numeric))


def _clamp_int(value: Any, min_value: int, max_value: int) -> int:
    try:
        numeric = int(value)
    except Exception:  # noqa: BLE001  # REASON: invalid outline integer inputs should fall back to the minimum outline scalar
        numeric = int(min_value)
    return max(min_value, min(max_value, numeric))
