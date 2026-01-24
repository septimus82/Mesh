from __future__ import annotations

import math
import random

import pytest

from engine.particles_core import sample_spawn_offset


def test_particles_spawn_shapes_circle() -> None:
    rng = random.Random(1234)
    cfg = {"shape": "circle", "radius_min": 0.0, "radius_max": 5.0}
    expected = [
        (-4.578521199573148, 1.7884300426247413),
        (0.3668118440495979, -0.22964281510557494),
        (-4.213313326874242, -2.393682465089723),
        (3.540682679412993, 2.0621962081490834),
        (0.3623726962627631, 4.362420125205523),
    ]
    outputs = [sample_spawn_offset(rng, cfg) for _ in range(len(expected))]
    for value, exp in zip(outputs, expected):
        assert value == pytest.approx(exp, abs=1e-6)
        assert math.hypot(value[0], value[1]) <= 5.0 + 1e-6
