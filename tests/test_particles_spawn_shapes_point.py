from __future__ import annotations

from engine.behaviours.particle_emitter import ParticleEmitter
from engine.particles_core import ParticleSystem


class _StubWindow:
    def __init__(self) -> None:
        self.particle_system = ParticleSystem()


class _StubEntity:
    def __init__(self) -> None:
        self.center_x = 10.0
        self.center_y = 20.0
        self.mesh_entity_data = {}


def test_particles_spawn_shapes_point() -> None:
    window = _StubWindow()
    entity = _StubEntity()
    emitter = ParticleEmitter(
        entity,
        window,
        mode="burst",
        count=4,
        spawn_shape="point",
        offset=[1.5, -2.0],
    )
    emitter.update(1.0 / 60.0)

    base_x = entity.center_x + 1.5
    base_y = entity.center_y - 2.0
    assert window.particle_system.particles
    for particle in window.particle_system.particles:
        assert particle.x == base_x
        assert particle.y == base_y
