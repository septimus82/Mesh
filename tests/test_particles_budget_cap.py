from __future__ import annotations

from engine.particles_core import ParticleData, ParticleSystem


def test_particles_budget_cap() -> None:
    system = ParticleSystem(max_particles=10)
    batch = [
        ParticleData(x=0.0, y=0.0, vx=0.0, vy=0.0, life=1.0)
        for _ in range(50)
    ]
    spawned = system.spawn(batch)
    assert spawned == 10
    assert system.alive_count == 10
    assert system.dropped_total > 0
