from __future__ import annotations

import math

import pytest

from engine.lighting.shadows_v1 import build_shadow_polygons_v1

pytestmark = pytest.mark.fast


def _dist(p: tuple[float, float]) -> float:
    return math.hypot(p[0], p[1])


def test_shadows_v1_geometry_basic_quad_build() -> None:
    light_pos = (0.0, 0.0)
    radius = 10.0
    occluder = [(5.0, 5.0), (6.0, 5.0), (6.0, 6.0), (5.0, 6.0)]

    polys = build_shadow_polygons_v1(light_pos, radius, [occluder])
    assert len(polys) == 2
    for poly in polys:
        assert len(poly) == 4
        for point in poly:
            assert math.isfinite(point[0])
            assert math.isfinite(point[1])

        near_a, near_b, far_b, far_a = poly
        assert _dist(far_a) >= _dist(near_a)
        assert _dist(far_b) >= _dist(near_b)
