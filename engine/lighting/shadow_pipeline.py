"""Shadow rendering helpers for the lighting system."""

from __future__ import annotations

import math
import os
from typing import Any

import engine.optional_arcade
from engine.arcade_compat import activate_framebuffer, clear_framebuffer, close_framebuffer_activation

from engine.log_once import log_once_with_counter
from engine.logging_tools import get_logger

from . import occluder_utils as _occluder_utils

logger = get_logger(__name__)
_SWALLOW_ONCE_TAGS: set[str] = set()


def _log_swallow(tag: str, where: str, purpose: str, *, once: bool = False) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    logger.debug("SWALLOW[%s] %s %s", tag, where, purpose, exc_info=True)


def _ambient_rgb_from_rgba(ambient: tuple[int, int, int, int] | tuple[int, int, int]) -> tuple[int, int, int]:
    if len(ambient) >= 3:
        return (int(ambient[0]), int(ambient[1]), int(ambient[2]))
    return (0, 0, 0)


def _draw_layer_target_compat(
    draw: Any,
    *,
    offset: tuple[float, float],
    target_fbo: Any,
    ambient_color: tuple[int, int, int, int] | tuple[int, int, int],
) -> bool:
    """Best-effort LightLayer.draw(...) call for target rendering across Arcade variants.

    Keep branch order deterministic and only fall back on signature mismatches.
    """
    rgb = _ambient_rgb_from_rgba(ambient_color)
    try:
        draw(position=offset, target=target_fbo, ambient_color=ambient_color)
        return True
    except TypeError:
        pass
    try:
        draw(target=target_fbo, ambient_color=ambient_color)
        return True
    except TypeError:
        pass
    # FBO is already activated by caller; these variants avoid requiring target kwarg.
    try:
        draw(position=offset, ambient_color=ambient_color)
        return True
    except TypeError:
        pass
    try:
        draw(ambient_color=ambient_color)
        return True
    except TypeError:
        pass
    try:
        draw(rgb)
        return True
    except TypeError:
        pass
    try:
        draw()
        return True
    except TypeError:
        return False


def _draw_layer_screen_compat(
    draw: Any,
    *,
    offset: tuple[float, float],
    ambient_color: tuple[int, int, int, int] | tuple[int, int, int],
) -> bool:
    """Best-effort LightLayer.draw(...) for on-screen fallback rendering."""
    rgb = _ambient_rgb_from_rgba(ambient_color)
    try:
        draw(position=offset, ambient_color=ambient_color)
        return True
    except TypeError:
        pass
    try:
        draw(ambient_color=ambient_color)
        return True
    except TypeError:
        pass
    try:
        draw(rgb)
        return True
    except TypeError:
        pass
    try:
        draw()
        return True
    except TypeError:
        return False


def end_hard_shadows_overlay(manager: Any) -> bool:
    """
    Ship-now hard shadow implementation: draw normal lighting, then overlay shadow polygons.

    This avoids fragile render target / mask compositing dependencies and produces an immediate,
    visible result in-game when occluders and a shadow-casting light are present.
    """
    layer = getattr(manager, "_layer", None)
    window = getattr(manager, "window", None)
    if layer is None:
        return False

    from .shadows import (  # noqa: PLC0415
        MAX_SHADOW_POLYS_PER_LIGHT,
        Viewport,
        build_shadow_polygons,
        cull_occluders_for_light,
        cull_polygons_for_light,
        render_shadow_mask,
    )
    from .shadows_v1 import build_shadow_polygons_v1  # noqa: PLC0415

    selected = manager._select_shadow_light()
    if selected is None:
        try:
            manager._draw_layer_safe()
        except Exception:  # noqa: BLE001  # REASON: shadow pipeline fallback
            _log_swallow(
                "SHDW-001",
                "engine.lighting.shadow_pipeline.end_hard_shadows_overlay",
                "draw_layer_safe_no_selected_light",
            )
        manager._last_lighting_stats = {
            "shadows_mode": manager.shadows_mode,
            "occluder_count": len(manager._static_occluders),
            "culled_occluder_count": 0,
            "shadow_poly_count": 0,
            "mask_rendered": False,
            "mask_backend": "overlay",
            "composite_ok": True,
            "fallback_drawn": False,
            "selected_shadow_light_type": None,
            "selected_shadow_light_pos": None,
            "selected_shadow_light_radius": None,
        }
        return True

    selected_type, (lx, ly), radius, _light_obj = selected
    if float(radius) <= 0:
        try:
            manager._draw_layer_safe()
        except Exception:  # noqa: BLE001  # REASON: shadow pipeline fallback
            _log_swallow(
                "SHDW-002",
                "engine.lighting.shadow_pipeline.end_hard_shadows_overlay",
                "draw_layer_safe_nonpositive_radius",
            )
        manager._last_lighting_stats = {
            "shadows_mode": manager.shadows_mode,
            "occluder_count": len(manager._static_occluders),
            "culled_occluder_count": 0,
            "shadow_poly_count": 0,
            "mask_rendered": False,
            "mask_backend": "overlay",
            "composite_ok": True,
            "fallback_drawn": False,
            "selected_shadow_light_type": selected_type,
            "selected_shadow_light_pos": [round(float(lx), 3), round(float(ly), 3)],
            "selected_shadow_light_radius": round(float(radius), 3),
        }
        return True

    rects, poly_occluders = _occluder_utils.build_rect_and_poly_occluders(
        getattr(manager, "_static_occluders", None) or []
    )

    culled_rects = cull_occluders_for_light(float(lx), float(ly), float(radius), rects)
    culled_polys = cull_polygons_for_light(float(lx), float(ly), float(radius), poly_occluders)
    rect_polys = build_shadow_polygons((float(lx), float(ly)), float(radius), culled_rects)
    poly_polys = build_shadow_polygons_v1((float(lx), float(ly)), float(radius), culled_polys)
    polys = rect_polys + poly_polys
    polys.sort(key=lambda p: (p[0][1], p[0][0], p[1][1], p[1][0]))
    if len(polys) > MAX_SHADOW_POLYS_PER_LIGHT:
        polys = polys[:MAX_SHADOW_POLYS_PER_LIGHT]

    cam = getattr(window, "camera", None)
    offset_x, offset_y = 0.0, 0.0
    if cam is not None:
        bottom_left = getattr(cam, "bottom_left", None)
        if isinstance(bottom_left, (tuple, list)) and len(bottom_left) >= 2:
            offset_x, offset_y = float(bottom_left[0]), float(bottom_left[1])
        else:
            pos = getattr(cam, "position", None)
            if isinstance(pos, (tuple, list)) and len(pos) >= 2:
                offset_x, offset_y = float(pos[0]), float(pos[1])

    viewport = Viewport(
        x=offset_x,
        y=offset_y,
        width=float(getattr(window, "width", 0) or 0),
        height=float(getattr(window, "height", 0) or 0),
    )

    try:
        manager._draw_layer_safe()
    except Exception:  # noqa: BLE001  # REASON: shadow pipeline fallback
        _log_swallow(
            "SHDW-003",
            "engine.lighting.shadow_pipeline.end_hard_shadows_overlay",
            "draw_layer_safe_before_mask",
        )

    drawn = 0
    try:
        render_shadow_mask(window, polys, viewport, target_texture=None, target_fbo=None)
        drawn = int(len(polys))
    except Exception:  # pragma: no cover - best-effort  # noqa: BLE001  # REASON: shadow pipeline fallback
        _log_swallow(
            "SHDW-004",
            "engine.lighting.shadow_pipeline.end_hard_shadows_overlay",
            "render_shadow_mask_overlay",
            once=True,
        )
        drawn = 0

    manager._last_lighting_stats = {
        "shadows_mode": manager.shadows_mode,
        "occluder_count": len(rects) + len(poly_occluders),
        "culled_occluder_count": len(culled_rects) + len(culled_polys),
        "shadow_poly_count": len(polys),
        "mask_rendered": bool(drawn),
        "mask_backend": "overlay",
        "composite_ok": True,
        "fallback_drawn": bool(drawn),
        "selected_shadow_light_type": selected_type,
        "selected_shadow_light_pos": [round(float(lx), 3), round(float(ly), 3)],
        "selected_shadow_light_radius": round(float(radius), 3),
    }
    return True


def draw_pending_shadow_fallback(manager: Any) -> None:
    if os.environ.get("MESH_SHADOWS_FALLBACK_DRAW", "1") != "1":
        return
    polys = getattr(manager, "_pending_shadow_fallback_polys", None)
    if not isinstance(polys, list) or not polys:
        return
    setattr(manager, "_pending_shadow_fallback_polys", [])
    if engine.optional_arcade.arcade is None:  # pragma: no cover
        return
    gl = getattr(engine.optional_arcade.arcade, "gl", None)
    if gl is not None:
        ctx = getattr(manager.window, "ctx", None)
        if ctx is not None and hasattr(ctx, "blend_func") and callable(getattr(ctx, "enable", None)):
            try:
                ctx.enable(ctx.BLEND)
            except Exception:  # noqa: BLE001  # REASON: shadow pipeline fallback
                _log_swallow(
                    "SHDW-005",
                    "engine.lighting.shadow_pipeline.draw_pending_shadow_fallback",
                    "ctx_enable_blend",
                    once=True,
                )
            try:
                ctx.blend_func = gl.BLEND_DEFAULT
            except Exception:  # noqa: BLE001  # REASON: shadow pipeline fallback
                _log_swallow(
                    "SHDW-006",
                    "engine.lighting.shadow_pipeline.draw_pending_shadow_fallback",
                    "set_blend_func",
                    once=True,
                )
    draw_poly = getattr(engine.optional_arcade.arcade, "draw_polygon_filled", None)
    if not callable(draw_poly):
        return
    for poly in polys:
        if not isinstance(poly, list) or len(poly) < 3:
            continue
        pts = [(float(x), float(y)) for x, y in poly]
        draw_poly(pts, (0, 0, 0, 140))


def draw_direct_shadows(manager: Any) -> None:
    """
    Debug/compat path: draw shadow quads directly onto the world view.

    This avoids render targets and compositing, and is best-effort (no-op if the
    engine.optional_arcade.arcade draw APIs are unavailable).
    """

    if engine.optional_arcade.arcade is None:  # pragma: no cover - defensive
        return

    selected = manager._select_shadow_light()
    if selected is None:
        manager._last_lighting_stats = {
            "shadows_mode": manager.shadows_mode,
            "occluder_count": len(manager._static_occluders),
            "culled_occluder_count": 0,
            "shadow_poly_count": 0,
            "mask_rendered": False,
            "selected_shadow_light_type": None,
            "selected_shadow_light_pos": None,
            "selected_shadow_light_radius": None,
        }
        return

    selected_type, (lx, ly), radius, _light_obj = selected
    if radius <= 0:
        return

    from .shadows import build_shadow_polygons, cull_occluders_for_light  # noqa: PLC0415
    rects = _occluder_utils.build_rect_occluders(manager._static_occluders)

    culled = cull_occluders_for_light(lx, ly, radius, rects)
    polys = build_shadow_polygons((lx, ly), radius, culled)

    draw_poly = getattr(engine.optional_arcade.arcade, "draw_polygon_filled", None)
    if not callable(draw_poly):
        return

    shadow_color = (0, 0, 0, 200)
    for poly in polys:
        try:
            draw_poly(poly, shadow_color)
        except Exception:  # noqa: BLE001  # REASON: shadow pipeline fallback
            _log_swallow(
                "SHDW-007",
                "engine.lighting.shadow_pipeline.draw_direct_shadows",
                "draw_polygon_filled",
                once=True,
            )
            continue

    manager._last_lighting_stats = {
        "shadows_mode": manager.shadows_mode,
        "occluder_count": len(rects),
        "culled_occluder_count": len(culled),
        "shadow_poly_count": len(polys),
        "mask_rendered": False,
        "selected_shadow_light_type": selected_type,
        "selected_shadow_light_pos": [round(float(lx), 3), round(float(ly), 3)],
        "selected_shadow_light_radius": round(float(radius), 3),
    }


def end_hard_shadows_composite(manager: Any) -> bool:
    """Arcade 3 hard-shadow path: render LightLayer light buffer, render a shadow mask, and composite.

    Returns True if the composite path ran successfully; False if it should fall back to LightLayer.draw().
    """
    layer = getattr(manager, "_layer", None)
    window = getattr(manager, "window", None)
    if layer is None:
        return False

    from .hard_shadows_backend import composite_to_window, ensure_render_targets  # noqa: PLC0415
    from .shadows import (  # noqa: PLC0415
        Viewport,
        build_shadow_polygons,
        cull_occluders_for_light,
        cull_polygons_for_light,
        render_shadow_mask,
    )
    from .shadows_v1 import build_shadow_polygons_v1  # noqa: PLC0415
    from .shadow_soften import expand_polygon  # noqa: PLC0415

    targets = ensure_render_targets(window, (int(getattr(window, "width", 0) or 0), int(getattr(window, "height", 0) or 0)))
    if targets is None:
        manager._last_lighting_stats = {
            "shadows_mode": manager.shadows_mode,
            "mask_rendered": False,
            "mask_backend": None,
            "mask_error": None,
            "mask_fallback_used": False,
            "composite_ok": False,
            "fallback_drawn": False,
            "hard_shadows_error": "targets_unavailable",
        }
        return False

    rects, poly_occluders = _occluder_utils.build_rect_and_poly_occluders(manager._static_occluders)

    if not rects and not poly_occluders:
        scene_controller = getattr(window, "scene_controller", None)
        scene_path = getattr(scene_controller, "current_scene_path", None) if scene_controller is not None else None
        key = f"hard_shadows_no_occluders:{scene_path}" if scene_path else "hard_shadows_no_occluders"
        log_once_with_counter(
            key,
            "Hard shadows enabled but no occluders present (need tilemap collision layer or explicit occluders).",
        )

    selected = manager._select_shadow_light()
    if selected is None:
        manager._last_lighting_stats = {
            "shadows_mode": manager.shadows_mode,
            "occluder_count": len(rects) + len(poly_occluders),
            "culled_occluder_count": 0,
            "shadow_poly_count": 0,
            "mask_rendered": False,
            "selected_shadow_light_type": None,
            "selected_shadow_light_pos": None,
            "selected_shadow_light_radius": None,
            "nearest_occluder_distance_est": None,
            "cull_square_intersects_any_occluder": False,
            "cull_tested_occluder_count": len(rects) + len(poly_occluders),
        }
        return False
    selected_type, (lx, ly), radius, _light_obj = selected
    if radius <= 0:
        return False

    cam = getattr(window, "camera", None)
    cam_pos = getattr(cam, "position", (0.0, 0.0)) if cam is not None else (0.0, 0.0)
    try:
        offset = (float(cam_pos[0]), float(cam_pos[1]))
    except Exception:  # noqa: BLE001  # REASON: shadow pipeline fallback
        _log_swallow(
            "SHDW-008",
            "engine.lighting.shadow_pipeline.end_hard_shadows_composite",
            "compute_camera_offset",
        )
        offset = (0.0, 0.0)

    light_activation_cm: Any | None = None
    try:
        backend, light_activation_cm = activate_framebuffer(targets.light_fbo, backend="auto")
        if backend != "none":
            clear_framebuffer(getattr(window, "ctx", None), targets.light_fbo, 0.0, 0.0, 0.0, 0.0)
    except Exception:  # noqa: BLE001  # REASON: shadow pipeline fallback
        _log_swallow(
            "SHDW-009",
            "engine.lighting.shadow_pipeline.end_hard_shadows_composite",
            "activate_or_clear_light_fbo",
            once=True,
        )

    draw = getattr(layer, "draw", None)
    if not callable(draw):
        close_framebuffer_activation(light_activation_cm)
        manager._last_lighting_stats = {
            "shadows_mode": manager.shadows_mode,
            "occluder_count": len(rects),
            "culled_occluder_count": 0,
            "shadow_poly_count": 0,
            "mask_rendered": False,
            "mask_backend": None,
            "mask_error": None,
            "mask_fallback_used": False,
            "composite_ok": False,
            "fallback_drawn": False,
            "hard_shadows_error": "layer_draw_missing",
        }
        return False
    try:
        draw_ok = _draw_layer_target_compat(
            draw,
            offset=offset,
            target_fbo=targets.light_fbo,
            ambient_color=manager._ambient_rgba(),
        )
        if not draw_ok:
            raise TypeError("LightLayer.draw signature unsupported for hard-shadow target render")
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        _log_swallow(
            "SHDW-010",
            "engine.lighting.shadow_pipeline.end_hard_shadows_composite",
            "draw_layer_target_compat",
            once=True,
        )
        close_framebuffer_activation(light_activation_cm)
        manager._last_lighting_stats = {
            "shadows_mode": manager.shadows_mode,
            "occluder_count": len(rects),
            "culled_occluder_count": 0,
            "shadow_poly_count": 0,
            "mask_rendered": False,
            "mask_backend": None,
            "mask_error": None,
            "mask_fallback_used": False,
            "composite_ok": False,
            "fallback_drawn": False,
            "hard_shadows_error": "layer_draw_failed",
        }
        return False
    try:
        manager._apply_light_cookies(target_fbo=targets.light_fbo, offset=offset)
    except Exception:  # noqa: BLE001  # REASON: shadow pipeline fallback
        _log_swallow(
            "SHDW-011",
            "engine.lighting.shadow_pipeline.end_hard_shadows_composite",
            "apply_light_cookies",
            once=True,
        )
    try:
        manager._apply_light_shafts(target_fbo=targets.light_fbo, offset=offset)
    except Exception:  # noqa: BLE001  # REASON: shadow pipeline fallback
        _log_swallow(
            "SHDW-012",
            "engine.lighting.shadow_pipeline.end_hard_shadows_composite",
            "apply_light_shafts",
            once=True,
        )
    close_framebuffer_activation(light_activation_cm)

    cull_debug: dict[str, Any] = {}
    culled = cull_occluders_for_light(lx, ly, radius, rects, debug=cull_debug)
    culled_polys = cull_polygons_for_light(lx, ly, radius, poly_occluders)
    rect_polys = build_shadow_polygons((lx, ly), radius, culled)
    poly_polys = build_shadow_polygons_v1((lx, ly), radius, culled_polys)
    polys = rect_polys + poly_polys
    soft_polys: list[list[tuple[float, float]]] = []
    cfg = getattr(window, "engine_config", None)
    soft_enabled = bool(getattr(cfg, "soft_shadows_enabled", False))
    runtime_settings = getattr(window, "runtime_settings", None)
    if runtime_settings is not None and hasattr(runtime_settings, "soft_shadows_enabled"):
        soft_enabled = bool(getattr(runtime_settings, "soft_shadows_enabled"))
    soft_expand_px = float(getattr(cfg, "soft_shadows_expand_px", 6.0))
    soft_alpha = float(getattr(cfg, "soft_shadows_alpha_scale", 0.35))
    if soft_enabled and soft_expand_px > 0.0 and polys:
        soft_polys = [expand_polygon(poly, soft_expand_px) for poly in polys]

    nearest_dist: float | None = None
    if rects:
        for r in rects:
            rx0 = float(r.x)
            ry0 = float(r.y)
            rx1 = rx0 + float(r.width)
            ry1 = ry0 + float(r.height)
            dx = max(rx0 - float(lx), 0.0, float(lx) - rx1)
            dy = max(ry0 - float(ly), 0.0, float(ly) - ry1)
            dist = math.hypot(dx, dy)
            if nearest_dist is None or dist < nearest_dist:
                nearest_dist = dist

    intersects_any = False
    if rects and radius > 0:
        left = float(lx) - float(radius)
        right = float(lx) + float(radius)
        bottom = float(ly) - float(radius)
        top = float(ly) + float(radius)
        for r in rects:
            rx0 = float(r.x)
            ry0 = float(r.y)
            rx1 = rx0 + float(r.width)
            ry1 = ry0 + float(r.height)
            if rx1 >= left and rx0 <= right and ry1 >= bottom and ry0 <= top:
                intersects_any = True
                break

    viewport = Viewport(
        x=float(offset[0]),
        y=float(offset[1]),
        width=float(getattr(window, "width", 0) or 0),
        height=float(getattr(window, "height", 0) or 0),
    )
    mask_tex = render_shadow_mask(
        window,
        polys,
        viewport,
        target_texture=targets.mask_tex,
        target_fbo=targets.mask_fbo,
    )
    if mask_tex is not None and soft_enabled and soft_polys:
        render_shadow_mask(
            window,
            soft_polys,
            viewport,
            target_texture=targets.mask_tex,
            target_fbo=targets.mask_fbo,
            alpha=soft_alpha,
            clear=False,
        )
    mask_backend = getattr(window, "_mesh_shadow_mask_backend", None)
    mask_error = getattr(window, "_mesh_shadow_mask_error", None) if os.environ.get("MESH_SHADOWS_TRACE") == "1" else None
    mask_fallback_used = False
    mask_rendered = mask_tex is not None
    if mask_tex is None:
        mask_fallback_used = True
        mask_tex = getattr(targets, "mask_tex", None)
        mask_activation_cm: Any | None = None
        try:
            fbo = getattr(targets, "mask_fbo", None)
            if fbo is not None:
                backend, mask_activation_cm = activate_framebuffer(fbo, backend="auto")
                if backend != "none":
                    clear_framebuffer(getattr(window, "ctx", None), fbo, 1.0, 1.0, 1.0, 1.0)
        except Exception:  # noqa: BLE001  # REASON: shadow pipeline fallback
            _log_swallow(
                "SHDW-013",
                "engine.lighting.shadow_pipeline.end_hard_shadows_composite",
                "activate_or_clear_mask_fbo_fallback",
                once=True,
            )
        finally:
            close_framebuffer_activation(mask_activation_cm)

    diffuse_tex = getattr(layer, "diffuse_texture", None)
    light_tex = getattr(targets, "light_tex", None)
    if diffuse_tex is None or light_tex is None:
        return bool(
            manager._draw_hard_shadow_fallback(
            draw=draw,
            offset=offset,
            viewport=viewport,
            polys=polys,
            stats={
                "shadows_mode": manager.shadows_mode,
                "occluder_count": len(rects) + len(poly_occluders),
                "culled_occluder_count": len(culled) + len(culled_polys),
                "shadow_poly_count": len(polys),
                "mask_rendered": False,
                "mask_backend": mask_backend,
                "mask_error": mask_error,
                "mask_fallback_used": bool(mask_fallback_used),
                "composite_ok": False,
                "selected_shadow_light_type": selected_type,
                "selected_shadow_light_pos": [round(float(lx), 3), round(float(ly), 3)],
                "selected_shadow_light_radius": round(float(radius), 3),
                "nearest_occluder_distance_est": None if nearest_dist is None else round(float(nearest_dist), 3),
                "cull_square_intersects_any_occluder": bool(intersects_any),
                "cull_tested_occluder_count": int(
                    cull_debug.get("tested_count", len(rects)) + len(poly_occluders)
                ),
                "hard_shadows_error": "missing_textures",
            },
            )
        )

    ok = bool(
        composite_to_window(
            window,
            diffuse_tex=diffuse_tex,
            light_tex=light_tex,
            mask_tex=mask_tex,
            ambient_color=manager._ambient_rgba(),
        )
    )
    if not ok:
        return bool(
            manager._draw_hard_shadow_fallback(
            draw=draw,
            offset=offset,
            viewport=viewport,
            polys=polys,
            stats={
                "shadows_mode": manager.shadows_mode,
                "occluder_count": len(rects) + len(poly_occluders),
                "culled_occluder_count": len(culled) + len(culled_polys),
                "shadow_poly_count": len(polys),
                "mask_rendered": False,
                "mask_backend": mask_backend,
                "mask_error": mask_error,
                "mask_fallback_used": bool(mask_fallback_used),
                "composite_ok": False,
                "selected_shadow_light_type": selected_type,
                "selected_shadow_light_pos": [round(float(lx), 3), round(float(ly), 3)],
                "selected_shadow_light_radius": round(float(radius), 3),
                "nearest_occluder_distance_est": None if nearest_dist is None else round(float(nearest_dist), 3),
                "cull_square_intersects_any_occluder": bool(intersects_any),
                "cull_tested_occluder_count": int(
                    cull_debug.get("tested_count", len(rects)) + len(poly_occluders)
                ),
                "hard_shadows_error": "composite_failed",
            },
            )
        )
    manager._last_lighting_stats = {
        "shadows_mode": manager.shadows_mode,
        "occluder_count": len(rects) + len(poly_occluders),
        "culled_occluder_count": len(culled) + len(culled_polys),
        "shadow_poly_count": len(polys),
        "mask_rendered": bool(mask_rendered) and bool(ok),
        "mask_backend": mask_backend,
        "mask_error": mask_error,
        "mask_fallback_used": bool(mask_fallback_used),
        "composite_ok": bool(ok),
        "fallback_drawn": False,
        "selected_shadow_light_type": selected_type,
        "selected_shadow_light_pos": [round(float(lx), 3), round(float(ly), 3)],
        "selected_shadow_light_radius": round(float(radius), 3),
        "nearest_occluder_distance_est": None if nearest_dist is None else round(float(nearest_dist), 3),
        "cull_square_intersects_any_occluder": bool(intersects_any),
        "cull_tested_occluder_count": int(
            cull_debug.get("tested_count", len(rects)) + len(poly_occluders)
        ),
    }
    return ok


def draw_hard_shadow_fallback(
    manager: Any,
    *,
    draw: Any,
    offset: tuple[float, float],
    viewport: Any,
    polys: list[list[tuple[float, float]]],
    stats: dict[str, Any],
) -> bool:
    """Forced visible hard-shadow fallback: draw LightLayer normally, then draw shadow quads as black overlays.

    Returns True only if at least one polygon was drawn (so LightManager.end will not overwrite it).
    """
    stats = dict(stats or {})
    stats.setdefault("mask_backend", "none")
    stats.setdefault("composite_ok", False)
    stats.setdefault("fallback_drawn", False)

    try:
        _draw_layer_screen_compat(
            draw,
            offset=offset,
            ambient_color=manager._ambient_rgba(),
        )
    except Exception:  # noqa: BLE001  # REASON: shadow pipeline fallback
        _log_swallow(
            "SHDW-014",
            "engine.lighting.shadow_pipeline.draw_hard_shadow_fallback",
            "draw_layer_screen_compat",
            once=True,
        )

    if os.environ.get("MESH_SHADOWS_FALLBACK_DRAW", "1") != "1":
        stats["fallback_drawn"] = False
        manager._last_lighting_stats = stats
        return False

    if engine.optional_arcade.arcade is None:  # pragma: no cover
        stats["fallback_drawn"] = False
        manager._last_lighting_stats = stats
        return False

    gl = getattr(engine.optional_arcade.arcade, "gl", None)
    if gl is not None:
        ctx = getattr(manager.window, "ctx", None)
        if ctx is not None and hasattr(ctx, "blend_func") and callable(getattr(ctx, "enable", None)):
            try:
                ctx.enable(ctx.BLEND)
            except Exception:  # noqa: BLE001  # REASON: shadow pipeline fallback
                _log_swallow(
                    "SHDW-015",
                    "engine.lighting.shadow_pipeline.draw_hard_shadow_fallback",
                    "ctx_enable_blend",
                    once=True,
                )
            try:
                ctx.blend_func = gl.BLEND_DEFAULT
            except Exception:  # noqa: BLE001  # REASON: shadow pipeline fallback
                _log_swallow(
                    "SHDW-016",
                    "engine.lighting.shadow_pipeline.draw_hard_shadow_fallback",
                    "set_blend_func",
                    once=True,
                )

    draw_poly = getattr(engine.optional_arcade.arcade, "draw_polygon_filled", None)
    if not callable(draw_poly):
        stats["fallback_drawn"] = False
        manager._last_lighting_stats = stats
        return False

    drawn = 0
    vx = float(getattr(viewport, "x", 0.0) or 0.0)
    vy = float(getattr(viewport, "y", 0.0) or 0.0)
    for poly in polys:
        if not isinstance(poly, list) or len(poly) < 3:
            continue
        pts = [(float(x - vx), float(y - vy)) for x, y in poly]
        try:
            draw_poly(pts, (0, 0, 0, 140))
            drawn += 1
        except Exception:  # noqa: BLE001  # REASON: shadow pipeline fallback
            _log_swallow(
                "SHDW-017",
                "engine.lighting.shadow_pipeline.draw_hard_shadow_fallback",
                "draw_polygon_filled",
                once=True,
            )
            continue

    stats["fallback_drawn"] = bool(drawn)
    manager._last_lighting_stats = stats
    return bool(drawn)
