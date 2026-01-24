from __future__ import annotations

from engine.lighting.occluders import Rect
from engine.lighting.shadows import cull_occluders_for_light


def test_shadow_occluder_culling_deterministic() -> None:
    rects = [
        Rect(x=-200.0, y=0.0, width=10.0, height=10.0),
        Rect(x=-5.0, y=-5.0, width=10.0, height=10.0),
        Rect(x=40.0, y=0.0, width=10.0, height=10.0),
        Rect(x=100.0, y=100.0, width=10.0, height=10.0),
        Rect(x=0.0, y=45.0, width=10.0, height=10.0),
    ]

    kept = cull_occluders_for_light(0.0, 0.0, 50.0, rects)
    kept2 = cull_occluders_for_light(0.0, 0.0, 50.0, rects)

    assert kept == kept2
    assert kept == [
        rects[1],
        rects[2],
        rects[4],
    ]

