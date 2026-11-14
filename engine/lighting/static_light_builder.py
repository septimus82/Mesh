"""Static light construction helpers for the lighting system."""

from __future__ import annotations

from typing import Any

from engine.swallowed_exceptions import _log_swallow

from .flicker import apply_flicker, flicker_state


def _light_seed(cfg: dict[str, Any], index: int) -> int:
    """A light's own flicker seed when it has none: from where it is, so neighbours don't flicker together."""
    try:
        x, y = int(float(cfg.get("x", 0))), int(float(cfg.get("y", 0)))
    except (TypeError, ValueError):
        x = y = 0
    return ((x * 73856093) ^ (y * 19349663) ^ (index * 83492791)) & 0x7FFFFFFF


def rebuild_static_and_dynamic_lights(manager: Any) -> None:
    manager._static_lights = []
    manager._static_count = 0
    manager._flicker_lights = []
    manager._light_casts_shadows = {}
    manager._shadow_occluders = None  # rebuilt from the room's occluders on the next shadowed frame

    use_shadow_mask = manager.shadowmask_enabled

    for cfg in manager._static_configs:
        if not bool(cfg.get("enabled", True)):
            continue
        if manager._max_static_lights is not None and manager._static_count >= manager._max_static_lights:
            continue

        if use_shadow_mask:
            points = manager._get_light_polygon_points(cfg)
            points = manager._round_points(points)
            if manager._is_valid_polygon(points):
                if manager._add_polygon_light(points, cfg):
                    manager._static_count += 1
                    continue
            else:
                manager._log_counter_once(
                    "invalid_polygon",
                    f"Invalid polygon for light {cfg.get('id', 'unknown')}, falling back to standard light.",
                )

        x = cfg.get("x", 0.0)
        y = cfg.get("y", 0.0)
        radius = cfg.get("radius", 100.0)
        color = manager._resolve_light_color(cfg)
        mode = cfg.get("mode", "soft")
        base_radius = float(radius)
        base_color = manager._normalize_color(color)
        light = manager._create_light(x, y, base_radius, base_color, mode)
        if light is not None:
            if bool(cfg.get("flicker_enabled", False)):
                seed_value = cfg.get("flicker_seed")
                try:
                    seed = int(seed_value) if seed_value is not None else _light_seed(cfg, len(manager._flicker_lights))
                except (TypeError, ValueError):
                    _log_swallow("SLBD-001", "engine/lighting/static_light_builder.py flicker seed", once=True)
                    seed = 0
                state = flicker_state(light, base_radius, base_color, {**cfg, "radius": base_radius}, seed)
                manager._flicker_lights.append(state)
                apply_flicker(state, manager._flicker_time, bool(getattr(manager, "reduced_flicker", False)))
            manager._static_lights.append(light)
            manager._add_light(light)
            manager._static_count += 1
            manager._light_casts_shadows[id(light)] = cfg.get("shadows", True) is not False

    for handle in manager._dynamic_handles:
        manager._add_light(handle.light)
        if handle.flicker_enabled:
            from . import _dynamic_flicker_settings  # noqa: PLC0415

            state = flicker_state(handle.light, handle.base_radius, handle.base_color, _dynamic_flicker_settings(handle),
                                  int(handle.flicker_seed or 0))
            manager._flicker_lights.append(state)
            apply_flicker(state, manager._flicker_time, bool(getattr(manager, "reduced_flicker", False)))
