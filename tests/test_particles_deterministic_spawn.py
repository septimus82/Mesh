from __future__ import annotations

import random

from engine.particles_core import RateAccumulator, spawn_radial_particles


def _simulate_spawn(seed: int) -> list[tuple[float, float, float, float, float]]:
    rng = random.Random(seed)
    accum = RateAccumulator()
    spawned = []
    dt = 1.0 / 60.0
    for _ in range(120):
        count = accum.step(30.0, dt)
        if count:
            spawned.extend(
                spawn_radial_particles(
                    rng,
                    count=count,
                    x=10.0,
                    y=20.0,
                    speed_min=1.0,
                    speed_max=3.0,
                    life_min=0.3,
                    life_max=0.6,
                    size=4.0,
                    color=(255, 255, 255, 255),
                )
            )
    return [(p.x, p.y, p.vx, p.vy, p.life) for p in spawned[:25]]


def test_particles_deterministic_spawn() -> None:
    first = _simulate_spawn(1337)
    second = _simulate_spawn(1337)
    assert first == second
