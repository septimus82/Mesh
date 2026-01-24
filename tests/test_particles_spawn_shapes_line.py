from __future__ import annotations

import random

import pytest

from engine.particles_core import sample_spawn_offset


def test_particles_spawn_shapes_line() -> None:
    rng = random.Random(333)
    cfg = {"shape": "line", "line_from": (1.0, 2.0), "line_to": (5.0, 2.0)}
    expected = [
        (3.2193418249728665, 2.0),
        (2.4125389819073213, 2.0),
        (4.932247650754446, 2.0),
        (1.328298964567205, 2.0),
        (3.150809035822073, 2.0),
    ]
    outputs = [sample_spawn_offset(rng, cfg) for _ in range(len(expected))]
    for value, exp in zip(outputs, expected):
        assert value == pytest.approx(exp, abs=1e-6)
        assert 1.0 <= value[0] <= 5.0
        assert value[1] == pytest.approx(2.0, abs=1e-6)
