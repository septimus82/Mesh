from __future__ import annotations

from engine.lighting.occluders import Rect
from engine.lighting.shadows import build_shadow_polygons


def test_shadow_polygon_build_deterministic() -> None:
    light_pos = (0.0, 5.0)
    radius = 50.0
    occluders = [Rect(x=10.0, y=0.0, width=10.0, height=10.0)]

    polys1 = build_shadow_polygons(light_pos, radius, occluders)
    polys2 = build_shadow_polygons(light_pos, radius, occluders)
    assert polys1 == polys2

    assert polys1 == [
        [
            (10.0, 0.0),
            (10.0, 10.0),
            (44.721, 27.361),
            (44.721, -17.361),
        ]
    ]

