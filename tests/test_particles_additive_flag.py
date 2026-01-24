from __future__ import annotations

from engine.behaviours.particle_emitter import ParticleEmitter
from engine.particles_core import ParticleSystem


class _StubWindow:
    def __init__(self) -> None:
        self.particle_system = ParticleSystem()


class _StubEntity:
    def __init__(self) -> None:
        self.center_x = 0.0
        self.center_y = 0.0
        self.mesh_entity_data = {}


def test_particles_additive_flag() -> None:
    window = _StubWindow()
    entity = _StubEntity()
    emitter = ParticleEmitter(entity, window, mode="burst", count=1, additive=True)
    emitter.update(1.0 / 60.0)
    assert window.particle_system.particles[0].additive is True

    window = _StubWindow()
    entity = _StubEntity()
    emitter = ParticleEmitter(entity, window, mode="burst", count=1)
    emitter.update(1.0 / 60.0)
    assert window.particle_system.particles[0].additive is False
