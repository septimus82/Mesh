"""Occluder collection helpers for shadow rendering."""

from __future__ import annotations

from typing import Any, Iterable

from .occluders import Rect


def build_rect_occluders(occluders: Iterable[dict[str, Any]]) -> list[Rect]:
    rects: list[Rect] = []
    for occ in occluders:
        if occ.get("type") == "poly":
            continue
        x = occ.get("x", 0.0)
        y = occ.get("y", 0.0)
        w = occ.get("width", 0.0)
        h = occ.get("height", 0.0)
        try:
            rects.append(Rect(x=float(x), y=float(y), width=float(w), height=float(h)))
        except Exception:  # noqa: BLE001  # REASON: malformed rect occluder values should skip only the invalid occluder entry
            continue
    rects.sort(key=lambda r: (r.y, r.x, r.height, r.width))
    return rects


def build_rect_and_poly_occluders(
    occluders: Iterable[dict[str, Any]],
) -> tuple[list[Rect], list[list[tuple[float, float]]]]:
    rects: list[Rect] = []
    poly_occluders: list[list[tuple[float, float]]] = []
    for occ in occluders:
        if not isinstance(occ, dict):
            continue
        if occ.get("type") == "poly":
            points = occ.get("points")
            if not isinstance(points, list):
                continue
            poly_points: list[tuple[float, float]] = []
            for entry in points:
                if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                    continue
                try:
                    poly_points.append((float(entry[0]), float(entry[1])))
                except Exception:  # noqa: BLE001  # REASON: malformed polygon point values should skip only the invalid polygon point
                    continue
            if len(poly_points) >= 3:
                poly_occluders.append(poly_points)
            continue
        try:
            rects.append(
                Rect(
                    x=float(occ.get("x", 0.0)),
                    y=float(occ.get("y", 0.0)),
                    width=float(occ.get("width", 0.0)),
                    height=float(occ.get("height", 0.0)),
                )
            )
        except Exception:  # noqa: BLE001  # REASON: malformed rect occluder values should skip only the invalid occluder entry
            continue
    rects.sort(key=lambda r: (r.y, r.x, r.height, r.width))
    return rects, poly_occluders
