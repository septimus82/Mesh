from __future__ import annotations

import pytest

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
            (109.443, 59.721),
            (122.361, 5.0),
            (109.443, -49.721),
        ]
    ]


@pytest.mark.fast
def test_a_wall_reaching_past_the_light_does_not_shade_the_lit_side() -> None:
    """A room's top wall seen from a light in the room: its corners lie beyond the radius. Projecting them onto the
    radius put the shadow's far edge between the light and the wall, shading the floor in front of it."""
    light, radius = (241.0, 240.0), 280.0
    (poly,) = build_shadow_polygons(light, radius, [Rect(x=0.0, y=448.0, width=640.0, height=32.0)])
    assert all(y >= 448.0 for _x, y in poly), poly  # all of it on the far side of the wall's near face

