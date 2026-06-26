"""Light cookie helper functions extracted from the lighting module."""

from __future__ import annotations

from typing import Any

import engine.optional_arcade
from engine.arcade_compat import activate_framebuffer, close_framebuffer_activation
from engine.swallowed_exceptions import _log_swallow


def normalize_cookie_offset(value: Any) -> tuple[float, float]:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        try:
            return (float(value[0]), float(value[1]))
        except Exception:  # noqa: BLE001  # REASON: lighting cookies fallback isolation
            _log_swallow("COOK-003", "cookie offset parse", once=True)
            return (0.0, 0.0)
    return (0.0, 0.0)


def collect_cookie_draw_specs(manager: Any, offset: tuple[float, float]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    try:
        offset_x = float(offset[0])
        offset_y = float(offset[1])
    except Exception:  # noqa: BLE001  # REASON: lighting cookies fallback isolation
        _log_swallow("COOK-004", "offset tuple parse", once=True)
        offset_x = 0.0
        offset_y = 0.0
    for cfg in getattr(manager, "_static_configs", []) or []:
        if not isinstance(cfg, dict):
            continue
        cookie_id = cfg.get("cookie_id")
        if not isinstance(cookie_id, str) or not cookie_id.strip():
            continue
        try:
            static_x = float(cfg.get("x", 0.0))
            static_y = float(cfg.get("y", 0.0))
            static_radius = float(cfg.get("radius", 0.0))
        except Exception:  # noqa: BLE001  # REASON: lighting cookies fallback isolation
            _log_swallow("COOK-005", "static config coords parse", once=True)
            continue
        offset_px = normalize_cookie_offset(cfg.get("cookie_offset_px"))
        specs.append(
            {
                "cookie_id": cookie_id.strip(),
                "center_x": static_x - offset_x + offset_px[0],
                "center_y": static_y - offset_y + offset_px[1],
                "radius": static_radius,
                "cookie_scale": float(cfg.get("cookie_scale", 1.0)),
                "cookie_rotation_deg": float(cfg.get("cookie_rotation_deg", 0.0)),
            }
        )
    for handle in getattr(manager, "_dynamic_handles", []) or []:
        cookie_id = getattr(handle, "cookie_id", None)
        if not isinstance(cookie_id, str) or not cookie_id.strip():
            continue
        light = getattr(handle, "light", None)
        light_x: float | None = None
        light_y: float | None = None
        if light is not None and hasattr(light, "position"):
            try:
                light_x, light_y = light.position
            except Exception:  # noqa: BLE001  # REASON: lighting cookies fallback isolation
                _log_swallow("COOK-006", "light position parse", once=True)
                light_x = None
                light_y = None
        if light_x is None or light_y is None:
            owner = getattr(handle, "owner", None)
            try:
                light_x = float(getattr(owner, "center_x", 0.0)) + float(getattr(handle, "offset_x", 0.0))
                light_y = float(getattr(owner, "center_y", 0.0)) + float(getattr(handle, "offset_y", 0.0))
            except Exception:  # noqa: BLE001  # REASON: lighting cookies fallback isolation
                _log_swallow("COOK-007", "owner center coords parse", once=True)
                light_x = 0.0
                light_y = 0.0
        dyn_radius = getattr(light, "radius", None)
        if dyn_radius is None:
            dyn_radius = getattr(handle, "base_radius", 0.0)
        try:
            if dyn_radius is None:
                dyn_radius = 0.0
            else:
                dyn_radius = float(dyn_radius)
        except Exception:  # noqa: BLE001  # REASON: lighting cookies fallback isolation
            _log_swallow("COOK-008", "dynamic radius parse", once=True)
            dyn_radius = 0.0
        offset_px = getattr(handle, "cookie_offset_px", (0.0, 0.0))
        if not isinstance(offset_px, tuple):
            offset_px = normalize_cookie_offset(offset_px)
        if light_x is None:
            light_x = 0.0
        if light_y is None:
            light_y = 0.0
        specs.append(
            {
                "cookie_id": cookie_id.strip(),
                "center_x": float(light_x) - offset_x + float(offset_px[0]),
                "center_y": float(light_y) - offset_y + float(offset_px[1]),
                "radius": dyn_radius,
                "cookie_scale": float(getattr(handle, "cookie_scale", 1.0)),
                "cookie_rotation_deg": float(getattr(handle, "cookie_rotation_deg", 0.0)),
            }
        )
    return specs


def load_cookie_texture(manager: Any, cookie_id: str) -> Any:
    if engine.optional_arcade.arcade is None:
        return None
    if cookie_id in manager._cookie_missing:
        return None
    cached = manager._cookie_textures.get(cookie_id)
    if cached is not None:
        return cached
    try:
        texture = engine.optional_arcade.arcade.load_texture(cookie_id)
    except Exception:  # noqa: BLE001  # REASON: lighting cookies fallback isolation
        _log_swallow("COOK-009", "load_texture call", once=True)
        texture = None
    if texture is None:
        manager._cookie_missing.add(cookie_id)
        return None
    manager._cookie_textures[cookie_id] = texture
    return texture


def apply_light_cookies(manager: Any, *, target_fbo: Any, offset: tuple[float, float]) -> int:
    specs = collect_cookie_draw_specs(manager, offset)
    if not specs:
        return 0
    if engine.optional_arcade.arcade is None:
        return 0
    draw_tex = engine.optional_arcade.draw_texture_rect_compat
    ctx = getattr(manager.window, "ctx", None)
    gl = engine.optional_arcade.arcade_gl
    multiply_available = False
    if ctx is not None and gl is not None and hasattr(ctx, "blend_func"):
        blend = getattr(gl, "BLEND_MULTIPLY", None)
        if blend is not None:
            try:
                ctx.enable(ctx.BLEND)
            except Exception:  # noqa: BLE001  # REASON: lighting cookies fallback isolation
                _log_swallow("COOK-001", "engine/lighting/cookies.py pass-only blanket swallow")
                pass
            try:
                ctx.blend_func = blend
                multiply_available = True
            except Exception:  # noqa: BLE001  # REASON: lighting cookies fallback isolation
                _log_swallow("COOK-010", "blend_func set", once=True)
                multiply_available = False
    if not multiply_available and not manager._cookie_blend_warned:
        manager._cookie_blend_warned = True
        print("[Mesh][Lighting] WARNING: cookie multiply blend unavailable; using normal blend")
    activation_cm = None
    try:
        if target_fbo is not None:
            _backend, activation_cm = activate_framebuffer(target_fbo, backend="auto")
        for spec in specs:
            cookie_id = spec["cookie_id"]
            texture = load_cookie_texture(manager, cookie_id)
            if texture is None:
                continue
            radius = max(0.0, float(spec.get("radius", 0.0)))
            scale = max(0.0, float(spec.get("cookie_scale", 1.0)))
            size = radius * 2.0 * scale
            if size <= 0.0:
                continue
            draw_tex(
                spec["center_x"],
                spec["center_y"],
                size,
                size,
                texture,
                angle=float(spec.get("cookie_rotation_deg", 0.0)),
                alpha=255,
            )
    finally:
        close_framebuffer_activation(activation_cm)
        if ctx is not None and gl is not None and hasattr(ctx, "blend_func"):
            try:
                ctx.blend_func = gl.BLEND_DEFAULT
            except Exception:  # noqa: BLE001  # REASON: lighting cookies fallback isolation
                _log_swallow("COOK-002", "engine/lighting/cookies.py pass-only blanket swallow")
                pass
    return len(specs)
