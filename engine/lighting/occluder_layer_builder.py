"""Occluder layer rebuild helpers for lighting."""

from __future__ import annotations

from typing import Any


def rebuild_occluder_layer(manager: Any) -> None:
    # Add occluders in a deterministic order and cache processed points for shadow casting.
    def _occ_sort_key_points(o: dict[str, Any]) -> tuple:
        k_id = o.get("id", "")
        k_type = o.get("type", "")
        if "points" in o:
            k_geom = tuple(c for p in o["points"] for c in p)
        else:
            k_geom = (o.get("x", 0), o.get("y", 0), o.get("width", 0), o.get("height", 0))
        return (k_id, k_type, k_geom)

    sorted_occluders = sorted(manager._static_occluders, key=_occ_sort_key_points)

    manager._processed_occluders = []
    for cfg in sorted_occluders:
        points: list[tuple[float, float]]
        if cfg.get("type") == "poly":
            points = cfg.get("points", [])
        else:
            x, y = cfg.get("x", 0), cfg.get("y", 0)
            w, h = cfg.get("width", 0), cfg.get("height", 0)
            points = [
                (x, y),
                (x + w, y),
                (x + w, y + h),
                (x, y + h),
            ]

        manager._processed_occluders.append({
            "id": cfg.get("id") or cfg.get("name"),
            "points": points,
        })

        manager._add_occluder(points)
