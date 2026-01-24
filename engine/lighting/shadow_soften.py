from __future__ import annotations

import math

Point = tuple[float, float]


def expand_polygon(points: list[Point], expand_px: float) -> list[Point]:
    if not points:
        return []
    expand = float(expand_px)
    if expand <= 0.0:
        return list(points)

    count = len(points)
    if count < 3:
        return list(points)

    cx = sum(p[0] for p in points) / count
    cy = sum(p[1] for p in points) / count
    out: list[Point] = []
    for x, y in points:
        dx = x - cx
        dy = y - cy
        dist = math.hypot(dx, dy)
        if dist <= 1e-6:
            out.append((x, y))
            continue
        scale = (dist + expand) / dist
        out.append((cx + dx * scale, cy + dy * scale))
    return out
