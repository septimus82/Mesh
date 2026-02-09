"""Polygon ray-casting helpers for light shapes."""

from __future__ import annotations

import math
from typing import Any


def cast_ray(manager: Any, origin: tuple[float, float], angle: float, max_radius: float) -> dict[str, Any]:
    ox, oy = origin
    dx = math.cos(angle)
    dy = math.sin(angle)

    closest_t = max_radius
    hit_occluder = None
    hit_point = (ox + dx * max_radius, oy + dy * max_radius)

    for occ in manager._processed_occluders:
        points = occ["points"]
        if len(points) < 2:
            continue

        for i in range(len(points)):
            p1 = points[i]
            p2 = points[(i + 1) % len(points)]

            x1, y1 = p1
            x2, y2 = p2

            vx = x2 - x1
            vy = y2 - y1
            wx = x1 - ox
            wy = y1 - oy

            det = dx * -vy - -vx * dy
            if abs(det) < 1e-9:
                continue

            t = (wx * -vy - -vx * wy) / det
            u = (dx * wy - wx * dy) / det

            if 0 <= u <= 1 and 0 < t < closest_t:
                closest_t = t
                hit_occluder = occ["id"]
                hit_point = (ox + t * dx, oy + t * dy)

    return {
        "angle": round(angle, 3),
        "hit": [round(hit_point[0], 3), round(hit_point[1], 3)],
        "hit_occluder": hit_occluder,
    }


def is_valid_polygon(points: list[tuple[float, float]]) -> bool:
    """Check if polygon is valid (non-degenerate, finite, non-zero area)."""
    if len(points) < 3:
        return False

    for p in points:
        if not (math.isfinite(p[0]) and math.isfinite(p[1])):
            return False

    unique = set()
    for p in points:
        unique.add((round(p[0], 3), round(p[1], 3)))
    if len(unique) < 3:
        return False

    area = 0.0
    for i in range(len(points)):
        j = (i + 1) % len(points)
        area += points[i][0] * points[j][1]
        area -= points[j][0] * points[i][1]
    area = abs(area) / 2.0

    return area > 1e-6


def round_points(points: list[tuple[float, float]], ndigits: int = 3) -> list[tuple[float, float]]:
    """Round all points to fixed precision for determinism."""
    return [(round(p[0], ndigits), round(p[1], ndigits)) for p in points]


def get_light_polygon_points(manager: Any, light_config: dict[str, Any]) -> list[tuple[float, float]]:
    """Calculate polygon points for a light based on shadow casting."""
    lx = light_config.get("x", 0.0)
    ly = light_config.get("y", 0.0)
    radius = light_config.get("radius", 100.0)

    angles = set()

    for i in range(16):
        angles.add(i * (2 * math.pi / 16))

    eps = 0.0005
    for occ in manager._processed_occluders:
        for px, py in occ["points"]:
            dx = px - lx
            dy = py - ly
            dist_sq = dx * dx + dy * dy
            if dist_sq > radius * radius:
                continue

            angle = math.atan2(dy, dx)
            angles.add(angle - eps)
            angles.add(angle)
            angles.add(angle + eps)

    normalized_angles = []
    for a in angles:
        a = a % (2 * math.pi)
        normalized_angles.append(a)

    normalized_angles.sort()

    unique_angles = []
    if normalized_angles:
        unique_angles.append(normalized_angles[0])
        for i in range(1, len(normalized_angles)):
            if normalized_angles[i] - unique_angles[-1] > 1e-6:
                unique_angles.append(normalized_angles[i])

    points = [(lx, ly)]

    for angle in unique_angles:
        ray_res = cast_ray(manager, (lx, ly), angle, radius)
        points.append(tuple(ray_res["hit"]))

    return points
