"""Static light construction helpers for the lighting system."""

from __future__ import annotations

from typing import Any

from engine.swallowed_exceptions import _log_swallow

from .flicker import FlickerNoise, apply_light_flicker
from .types import _FlickerLightState


def rebuild_static_and_dynamic_lights(manager: Any) -> None:
    manager._static_lights = []
    manager._static_count = 0
    manager._flicker_lights = []

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
            flicker_enabled = bool(cfg.get("flicker_enabled", False))
            if flicker_enabled:
                seed_value = cfg.get("flicker_seed")
                if seed_value is None:
                    seed_value = len(manager._flicker_lights)
                try:
                    seed = int(seed_value)
                except Exception:  # noqa: BLE001  # REASON: malformed flicker seed values should fall back to a deterministic zero seed
                    _log_swallow("SLBD-001", "engine/lighting/static_light_builder.py blanket swallow", once=True)
                    seed = 0
                speed = float(cfg.get("flicker_speed", 1.0))
                amount = float(cfg.get("flicker_amount", 0.0))
                radius_px = cfg.get("flicker_radius_px")
                intensity = cfg.get("flicker_intensity")
                if radius_px is not None:
                    try:
                        radius_px = float(radius_px)
                    except Exception:  # noqa: BLE001  # REASON: malformed flicker radius overrides should fall back to the base light radius
                        _log_swallow("SLBD-002", "engine/lighting/static_light_builder.py blanket swallow", once=True)
                        radius_px = None
                if intensity is not None:
                    try:
                        intensity = float(intensity)
                    except Exception:  # noqa: BLE001  # REASON: malformed flicker intensity overrides should fall back to the base light color intensity
                        _log_swallow("SLBD-003", "engine/lighting/static_light_builder.py blanket swallow", once=True)
                        intensity = None
                state = _FlickerLightState(
                    light=light,
                    base_radius=base_radius,
                    base_color=base_color,
                    noise=FlickerNoise(seed),
                    speed=speed,
                    amount=amount,
                    radius_px=radius_px,
                    intensity=intensity,
                )
                manager._flicker_lights.append(state)
                flicker_radius, flicker_color = apply_light_flicker(
                    base_radius=state.base_radius,
                    base_color=state.base_color,
                    noise=state.noise,
                    time_s=manager._flicker_time,
                    speed=state.speed,
                    amount=state.amount,
                    radius_px=state.radius_px,
                    intensity=state.intensity,
                )
                if hasattr(light, "radius"):
                    light.radius = flicker_radius
                if hasattr(light, "color"):
                    light.color = flicker_color
            manager._static_lights.append(light)
            manager._add_light(light)
            manager._static_count += 1

    for handle in manager._dynamic_handles:
        manager._add_light(handle.light)
        if handle.flicker_enabled:
            seed = 0 if handle.flicker_seed is None else int(handle.flicker_seed)
            radius_px = handle.flicker_radius_px
            if radius_px is not None:
                try:
                    radius_px = float(radius_px)
                except Exception:  # noqa: BLE001  # REASON: malformed dynamic flicker radius overrides should fall back to the base light radius
                    _log_swallow("SLBD-004", "engine/lighting/static_light_builder.py blanket swallow", once=True)
                    radius_px = None
            intensity = handle.flicker_intensity
            if intensity is not None:
                try:
                    intensity = float(intensity)
                except Exception:  # noqa: BLE001  # REASON: malformed dynamic flicker intensity overrides should fall back to the base light color intensity
                    _log_swallow("SLBD-005", "engine/lighting/static_light_builder.py blanket swallow", once=True)
                    intensity = None
            state = _FlickerLightState(
                light=handle.light,
                base_radius=handle.base_radius,
                base_color=handle.base_color,
                noise=FlickerNoise(seed),
                speed=float(handle.flicker_speed),
                amount=float(handle.flicker_amount),
                radius_px=radius_px,
                intensity=intensity,
            )
            manager._flicker_lights.append(state)
            flicker_radius, flicker_color = apply_light_flicker(
                base_radius=state.base_radius,
                base_color=state.base_color,
                noise=state.noise,
                time_s=manager._flicker_time,
                speed=state.speed,
                amount=state.amount,
                radius_px=state.radius_px,
                intensity=state.intensity,
            )
            if hasattr(handle.light, "radius"):
                handle.light.radius = flicker_radius
            if hasattr(handle.light, "color"):
                handle.light.color = flicker_color
