from __future__ import annotations

import random

import pytest

from engine.particles_core import sample_spawn_offset


def test_particles_spawn_shapes_box() -> None:
    rng = random.Random(222)
    cfg = {"shape": "box", "box_w": 4.0, "box_h": 2.0}
    expected = [
        (1.1152657302587805, -0.5295092272171971),
        (-0.7754943361424842, -0.9416137563933749),
        (-1.1080088184784205, 0.4804084408315734),
        (-0.234782831306787, -0.8498458001740894),
        (-1.9350056319853115, 0.8727862450233603),
    ]
    outputs = [sample_spawn_offset(rng, cfg) for _ in range(len(expected))]
    for value, exp in zip(outputs, expected):
        assert value == pytest.approx(exp, abs=1e-6)
        assert -2.0 <= value[0] <= 2.0
        assert -1.0 <= value[1] <= 1.0
