"""Shadow rendering helpers for the lighting system."""

from __future__ import annotations

from typing import Any

import engine.optional_arcade
from engine.logging_tools import get_logger
from engine.swallowed_exceptions import _log_swallow

from . import occluder_utils as _occluder_utils

logger = get_logger(__name__)


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
    )
    from .shadows_v1 import build_shadow_polygons_v1  # noqa: PLC0415

    selected = manager._select_shadow_light()
    if selected is None:
        try:
            manager._draw_layer_safe()
        except Exception:  # noqa: BLE001  # REASON: shadow pipeline fallback
            _log_swallow(
                "SHDW-001",
                "engine.lighting.shadow_pipeline.end_hard_shadows_overlay draw_layer_safe_no_selected_light",
                once=False,
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
                "engine.lighting.shadow_pipeline.end_hard_shadows_overlay draw_layer_safe_nonpositive_radius",
                once=False,
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
            "engine.lighting.shadow_pipeline.end_hard_shadows_overlay draw_layer_safe_before_mask",
            once=False,
        )

    drawn = 0
    draw_poly = getattr(engine.optional_arcade.arcade, "draw_polygon_filled", None)
    if callable(draw_poly):
        # Shadows are in world coordinates, like the lights: draw them through the world camera (scroll and
        # zoom), then return to the GUI camera end() runs under. Subtracting the camera's corner ignored zoom,
        # so at any zoom but 1 the shadows were drawn away from their occluders.
        use_world_camera = getattr(getattr(window, "camera", None), "use", None)
        through_camera = callable(use_world_camera)
        vx, vy = (0.0, 0.0) if through_camera else (float(viewport.x), float(viewport.y))
        if use_world_camera is not None and through_camera:
            use_world_camera()
        try:
            for poly in polys:
                if not isinstance(poly, list) or len(poly) < 3:
                    continue
                pts = [(float(x - vx), float(y - vy)) for x, y in poly]
                try:
                    draw_poly(pts, (0, 0, 0, 180))
                    drawn += 1
                except Exception:  # pragma: no cover  # noqa: BLE001  # REASON: shadow pipeline fallback
                    _log_swallow(
                        "SHDW-004",
                        "engine.lighting.shadow_pipeline.end_hard_shadows_overlay draw_polygon_filled",
                        once=True,
                    )
        finally:
            restore = getattr(getattr(window, "camera_controller", None), "use_gui_camera", None)
            if through_camera and callable(restore):
                restore()

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
                "engine.lighting.shadow_pipeline.draw_direct_shadows draw_polygon_filled",
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
