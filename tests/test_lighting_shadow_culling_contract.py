from __future__ import annotations

import pytest

from engine.lighting.shadows_v1 import build_shadow_polygons_v1

pytestmark = pytest.mark.fast


def test_shadows_v1_culls_far_occluders() -> None:
    light_pos = (0.0, 0.0)
    radius = 5.0
    far_occluder = [(100.0, 100.0), (110.0, 100.0), (110.0, 110.0), (100.0, 110.0)]

    polys = build_shadow_polygons_v1(light_pos, radius, [far_occluder])
    assert polys == []
