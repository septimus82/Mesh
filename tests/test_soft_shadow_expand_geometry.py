from __future__ import annotations

import math

import pytest

from engine.lighting.shadow_soften import expand_polygon

pytestmark = pytest.mark.fast


def _centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    return cx, cy


def test_soft_shadow_expand_increases_distance() -> None:
    quad = [(0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0)]
    expanded = expand_polygon(quad, 1.0)
    assert len(expanded) == len(quad)

    cx, cy = _centroid(quad)
    before = sum(math.hypot(p[0] - cx, p[1] - cy) for p in quad) / len(quad)
    after = sum(math.hypot(p[0] - cx, p[1] - cy) for p in expanded) / len(expanded)
    assert after > before

    for x, y in expanded:
        assert math.isfinite(x)
        assert math.isfinite(y)
