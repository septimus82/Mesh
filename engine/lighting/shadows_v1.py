from __future__ import annotations

import math
from typing import Sequence

from engine.geometry_tools import sanitize_poly

Point = tuple[float, float]
Polygon = list[Point]

MAX_SHADOW_POLYS_PER_LIGHT = 512


def _polygon_winding(points: Sequence[Point]) -> float:
    area = 0.0
    count = len(points)
    for i in range(count):
        x0, y0 = points[i]
        x1, y1 = points[(i + 1) % count]
        area += (x0 * y1) - (x1 * y0)
    return area * 0.5


def _bbox_intersects_square(points: Sequence[Point], lx: float, ly: float, r: float) -> bool:
    left = lx - r
    right = lx + r
    bottom = ly - r
    top = ly + r

    min_x = min(p[0] for p in points)
    max_x = max(p[0] for p in points)
    min_y = min(p[1] for p in points)
    max_y = max(p[1] for p in points)

    return max_x >= left and min_x <= right and max_y >= bottom and min_y <= top


def cull_polygons_for_light(
    light_x: float,
    light_y: float,
    radius: float,
    polygons: Sequence[Polygon],
) -> list[Polygon]:
    lx = float(light_x)
    ly = float(light_y)
    r = float(radius)
    if r <= 0.0:
        return []

    kept: list[Polygon] = []
    for poly in polygons:
        points = sanitize_poly(poly)
        if len(points) < 3:
            continue
        if _bbox_intersects_square(points, lx, ly, r):
            kept.append(points)
    return kept


def build_shadow_polygons_v1(
    light_pos: Point,
    light_radius: float,
    occluder_polys: Sequence[Polygon],
) -> list[Polygon]:
    lx, ly = float(light_pos[0]), float(light_pos[1])
    radius = float(light_radius)
    if radius <= 0.0:
        return []

    polys_out: list[Polygon] = []
    for poly in occluder_polys:
        points = sanitize_poly(poly)
        if len(points) < 3:
            continue
        if not _bbox_intersects_square(points, lx, ly, radius):
            continue

        winding = _polygon_winding(points)
        if winding == 0.0:
            continue
        outward_sign = 1.0 if winding > 0.0 else -1.0

        count = len(points)
        for i in range(count):
            p0 = points[i]
            p1 = points[(i + 1) % count]
            dx = p1[0] - p0[0]
            dy = p1[1] - p0[1]
            if dx == 0.0 and dy == 0.0:
                continue

            if outward_sign > 0.0:
                nx, ny = dy, -dx
            else:
                nx, ny = -dy, dx

            lx_vec = lx - p0[0]
            ly_vec = ly - p0[1]
            dot = nx * lx_vec + ny * ly_vec
            if dot >= 0.0:
                continue

            def _extrude(p: Point) -> Point:
                vx = p[0] - lx
                vy = p[1] - ly
                dist = math.hypot(vx, vy)
                if dist <= 1e-9:
                    return (lx, ly)
                far_dist = max(radius, dist)
                scale = far_dist / dist
                return (lx + vx * scale, ly + vy * scale)

            far0 = _extrude(p0)
            far1 = _extrude(p1)
            polys_out.append([p0, p1, far1, far0])

    polys_out = [
        [(round(x, 3), round(y, 3)) for x, y in poly]
        for poly in polys_out
    ]

    if len(polys_out) > MAX_SHADOW_POLYS_PER_LIGHT:
        polys_out = polys_out[:MAX_SHADOW_POLYS_PER_LIGHT]
    return polys_out
