"""Lighting snapshot helpers for debug/state reporting."""

from __future__ import annotations

from typing import Any

from . import shadowcast_snapshot as _shadowcast_snapshot


def build_lighting_snapshot(manager: Any) -> dict[str, Any]:
    snapshot_lights = []
    for light in manager._static_configs:
        clean_light = {
            k: v for k, v in light.items()
            if k in {"type", "color", "intensity", "x", "y", "radius", "mode"}
        }
        if "color" in clean_light:
            clean_light["color"] = list(clean_light["color"])
        snapshot_lights.append(clean_light)

    snapshot_occluders: list[dict[str, Any]] = []
    for occ in manager._static_occluders:
        oid = occ.get("id") or occ.get("name")
        otype = occ.get("type", "rect")

        summary: dict[str, Any] = {
            "type": otype,
        }
        if oid:
            summary["id"] = oid

        if otype == "poly":
            points = occ.get("points", [])
            summary["points_count"] = len(points)
            if points:
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                summary["bbox"] = [min(xs), min(ys), max(xs), max(ys)]
            else:
                summary["bbox"] = [0, 0, 0, 0]
        else:
            x = occ.get("x", 0)
            y = occ.get("y", 0)
            w = occ.get("width", 0)
            h = occ.get("height", 0)
            summary["rect"] = [x, y, w, h]

        snapshot_occluders.append(summary)

    def _occ_sort_key(o: dict[str, Any]) -> tuple:
        k_id = o.get("id", "")
        k_type = o.get("type", "")
        if "bbox" in o:
            k_geom = tuple(o["bbox"])
        else:
            k_geom = tuple(o.get("rect", []))
        return (k_id, k_type, k_geom)

    snapshot_occluders.sort(key=_occ_sort_key)

    result = {
        "enabled": manager.enabled,
        "ambient_color": list(manager.ambient_color),
        "lights": snapshot_lights,
        "light_count": len(snapshot_lights),
        "occluders": snapshot_occluders,
        "occluder_count": len(snapshot_occluders),
    }

    if manager.shadowcast_debug_enabled:
        result["shadowcast"] = _shadowcast_snapshot.build_shadowcast_snapshot(manager)

    return result
