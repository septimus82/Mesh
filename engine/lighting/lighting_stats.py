"""Lighting statistics aggregation helpers."""

from __future__ import annotations

import math
import os
from typing import Any

from . import occluder_utils as _occluder_utils


def build_lighting_stats(manager: Any) -> dict[str, Any]:
    stats = dict(getattr(manager, "_last_lighting_stats", None) or {})
    stats.setdefault("shadows_mode", manager.shadows_mode)
    stats.setdefault("static_light_count", len(manager._static_lights))
    stats.setdefault("dynamic_light_count", len(manager._dynamic_handles))
    stats.setdefault(
        "occluder_count",
        sum(
            1
            for occ in (getattr(manager, "_static_occluders", None) or [])
            if isinstance(occ, dict) and occ.get("type") != "poly"
        ),
    )
    stats.setdefault("culled_occluder_count", 0)
    stats.setdefault("cull_tested_occluder_count", 0)
    stats.setdefault("cull_kept_occluder_count", 0)
    stats.setdefault("shadow_poly_count", 0)
    stats.setdefault("mask_rendered", False)
    stats.setdefault("mask_backend", None)
    stats.setdefault("mask_error", None)
    stats.setdefault("mask_fallback_used", False)
    stats.setdefault("composite_ok", None)
    stats.setdefault("fallback_drawn", False)
    stats.setdefault("hard_shadows_error", None)

    if manager.shadows_mode == "hard" and stats.get("selected_shadow_light_type") is None:
        selected = manager._select_shadow_light()
        if selected is not None:
            kind, (lx, ly), radius, _light_obj = selected
            stats.setdefault("selected_shadow_light_type", kind)
            stats.setdefault("selected_shadow_light_pos", [round(float(lx), 3), round(float(ly), 3)])
            stats.setdefault("selected_shadow_light_radius", round(float(radius), 3))

            from .shadows import build_shadow_polygons, cull_occluders_for_light  # noqa: PLC0415

            rects = _occluder_utils.build_rect_occluders(getattr(manager, "_static_occluders", None) or [])

            nearest_dist: float | None = None
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
            stats.setdefault("nearest_occluder_distance_est", None if nearest_dist is None else round(float(nearest_dist), 3))

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
            stats.setdefault("cull_square_intersects_any_occluder", bool(intersects_any))

            cull_debug: dict[str, Any] = {}
            culled = cull_occluders_for_light(lx, ly, radius, rects, debug=cull_debug)
            stats["culled_occluder_count"] = int(len(culled))
            stats["cull_tested_occluder_count"] = int(cull_debug.get("tested_count", len(rects)))
            stats["cull_kept_occluder_count"] = int(cull_debug.get("kept_count", len(culled)))
            stats["shadow_poly_count"] = int(len(build_shadow_polygons((lx, ly), radius, culled)))
        else:
            stats.setdefault("selected_shadow_light_type", None)
            stats.setdefault("selected_shadow_light_pos", None)
            stats.setdefault("selected_shadow_light_radius", None)

            if bool(getattr(manager, "debug_geometry_enabled", False) or getattr(manager, "shadowcast_debug_enabled", False)):
                stats.setdefault("shadow_light_skip_reasons", list(getattr(manager, "_last_shadow_light_skip_reasons", []) or []))

    try:
        stats.setdefault("mask_backend", getattr(manager.window, "_mesh_shadow_mask_backend", None))
        if os.environ.get("MESH_SHADOWS_TRACE") == "1":
            stats.setdefault("mask_error", getattr(manager.window, "_mesh_shadow_mask_error", None))
    except Exception:  # noqa: BLE001
        pass
    return stats
