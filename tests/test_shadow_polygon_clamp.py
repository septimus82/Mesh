from __future__ import annotations

from engine.lighting.occluders import Rect
from engine.lighting.shadows import MAX_SHADOW_POLYS_PER_LIGHT, build_shadow_polygons


def test_shadow_polygon_clamp() -> None:
    rects: list[Rect] = []
    for i in range(MAX_SHADOW_POLYS_PER_LIGHT + 50):
        rects.append(Rect(x=float(i), y=0.0, width=1.0, height=1.0))

    polys1 = build_shadow_polygons((0.0, 0.0), 100.0, rects)
    polys2 = build_shadow_polygons((0.0, 0.0), 100.0, rects)

    assert len(polys1) == MAX_SHADOW_POLYS_PER_LIGHT
    assert polys1 == polys2

