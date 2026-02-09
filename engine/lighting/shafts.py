"""Light shaft helper functions extracted from the lighting module."""

from __future__ import annotations

from typing import Any

import engine.optional_arcade

from .flicker import FlickerNoise, apply_light_flicker


def collect_shafts_draw_specs(manager: Any, offset: tuple[float, float]) -> list[dict[str, Any]]:
    from .light_shafts import build_shafts_params  # noqa: PLC0415

    specs: list[dict[str, Any]] = []
    try:
        offset_x = float(offset[0])
        offset_y = float(offset[1])
    except Exception:  # noqa: BLE001
        offset_x = 0.0
        offset_y = 0.0

    flicker_index = 0
    static_count = 0
    for cfg in getattr(manager, "_static_configs", []) or []:
        if not isinstance(cfg, dict):
            continue
        if not bool(cfg.get("enabled", True)):
            continue
        if manager._max_static_lights is not None and static_count >= manager._max_static_lights:
            continue
        try:
            light_x = float(cfg.get("x", 0.0))
            light_y = float(cfg.get("y", 0.0))
            radius = float(cfg.get("radius", 0.0))
        except Exception:  # noqa: BLE001
            continue
        static_count += 1
        color = manager._resolve_light_color(cfg)
        if bool(cfg.get("flicker_enabled", False)):
            seed_value = cfg.get("flicker_seed")
            if seed_value is None:
                seed_value = flicker_index
            try:
                seed = int(seed_value)
            except Exception:  # noqa: BLE001
                seed = 0
            flicker_index += 1
            speed = float(cfg.get("flicker_speed", 1.0))
            amount = float(cfg.get("flicker_amount", 0.0))
            radius_px = cfg.get("flicker_radius_px")
            intensity = cfg.get("flicker_intensity")
            try:
                radius_px = float(radius_px) if radius_px is not None else None
            except Exception:  # noqa: BLE001
                radius_px = None
            try:
                intensity = float(intensity) if intensity is not None else None
            except Exception:  # noqa: BLE001
                intensity = None
            noise = FlickerNoise(seed)
            _radius, color = apply_light_flicker(
                base_radius=radius,
                base_color=color,
                noise=noise,
                time_s=manager._flicker_time,
                speed=speed,
                amount=amount,
                radius_px=radius_px,
                intensity=intensity,
            )
        params = build_shafts_params(
            (light_x - offset_x, light_y - offset_y),
            color,
            radius,
            cfg,
            manager._flicker_time,
        )
        if params is not None:
            specs.append(params)

    for handle in getattr(manager, "_dynamic_handles", []) or []:
        if not bool(getattr(handle, "shafts_enabled", False)):
            continue
        light = getattr(handle, "light", None)
        dyn_x = 0.0
        dyn_y = 0.0
        got_position = False
        if light is not None and hasattr(light, "position"):
            try:
                dyn_x, dyn_y = light.position
                got_position = True
            except Exception:  # noqa: BLE001
                dyn_x = 0.0
                dyn_y = 0.0
        if not got_position:
            owner = getattr(handle, "owner", None)
            try:
                dyn_x = float(getattr(owner, "center_x", 0.0)) + float(getattr(handle, "offset_x", 0.0))
                dyn_y = float(getattr(owner, "center_y", 0.0)) + float(getattr(handle, "offset_y", 0.0))
            except Exception:  # noqa: BLE001
                dyn_x = 0.0
                dyn_y = 0.0
        dyn_radius = getattr(light, "radius", None)
        if dyn_radius is None:
            dyn_radius = getattr(handle, "base_radius", 0.0)
        try:
            dyn_radius = float(dyn_radius or 0.0)
        except Exception:  # noqa: BLE001
            dyn_radius = 0.0
        base_color = getattr(handle, "color_rgba", None) or getattr(handle, "base_color", (255, 255, 255, 255))
        color = manager._normalize_color(base_color)
        if bool(getattr(handle, "flicker_enabled", False)):
            seed = 0 if handle.flicker_seed is None else int(handle.flicker_seed)
            radius_px = getattr(handle, "flicker_radius_px", None)
            try:
                radius_px = float(radius_px) if radius_px is not None else None
            except Exception:  # noqa: BLE001
                radius_px = None
            intensity = getattr(handle, "flicker_intensity", None)
            try:
                intensity = float(intensity) if intensity is not None else None
            except Exception:  # noqa: BLE001
                intensity = None
            noise = FlickerNoise(seed)
            _radius, color = apply_light_flicker(
                base_radius=dyn_radius,
                base_color=color,
                noise=noise,
                time_s=manager._flicker_time,
                speed=float(getattr(handle, "flicker_speed", 1.0)),
                amount=float(getattr(handle, "flicker_amount", 0.0)),
                radius_px=radius_px,
                intensity=intensity,
            )
        params = build_shafts_params(
            (float(dyn_x) - offset_x, float(dyn_y) - offset_y),
            color,
            dyn_radius,
            {
                "shafts_enabled": getattr(handle, "shafts_enabled", False),
                "shafts_length_px": getattr(handle, "shafts_length_px", 220.0),
                "shafts_width_px": getattr(handle, "shafts_width_px", 140.0),
                "shafts_rotation_deg": getattr(handle, "shafts_rotation_deg", 0.0),
                "shafts_alpha": getattr(handle, "shafts_alpha", 0.35),
                "shafts_noise_speed": getattr(handle, "shafts_noise_speed", 0.08),
                "shafts_noise_amount": getattr(handle, "shafts_noise_amount", 0.15),
            },
            manager._flicker_time,
        )
        if params is not None:
            specs.append(params)

    return specs


def apply_light_shafts(manager: Any, *, target_fbo: Any, offset: tuple[float, float]) -> int:
    specs = collect_shafts_draw_specs(manager, offset)
    if not specs:
        return 0
    if engine.optional_arcade.arcade is None:
        return 0
    draw_rect = getattr(engine.optional_arcade.arcade, "draw_rectangle_filled", None)
    if not callable(draw_rect):
        return 0
    try:
        if target_fbo is not None:
            try:
                target_fbo.use()
            except Exception:  # noqa: BLE001
                pass
        for spec in specs:
            color = spec.get("color_rgba")
            if not isinstance(color, (list, tuple)) or len(color) < 4:
                color = (255, 255, 255, 0)
            if int(color[3]) <= 0:
                continue
            draw_rect(
                float(spec.get("center_x", 0.0)),
                float(spec.get("center_y", 0.0)),
                float(spec.get("width_px", 0.0)),
                float(spec.get("length_px", 0.0)),
                color,
                float(spec.get("rotation_deg", 0.0)),
            )
    except Exception:  # noqa: BLE001
        return 0
    return len(specs)
