from __future__ import annotations

from engine.behaviours.particle_emitter import ParticleEmitter
from engine.particles_core import ParticleSystem, appearance_key


class _StubWindow:
    def __init__(self) -> None:
        self.particle_system = ParticleSystem()


class _StubEntity:
    def __init__(self) -> None:
        self.center_x = 1.0
        self.center_y = 2.0
        self.mesh_entity_data = {}


def test_particles_atlas_rect_direct() -> None:
    window = _StubWindow()
    entity = _StubEntity()
    emitter = ParticleEmitter(
        entity,
        window,
        mode="burst",
        count=1,
        sprite="packs/core/fx/spark.png",
        rect=[2, 4, 8, 16],
    )
    emitter.update(1.0 / 60.0)

    assert window.particle_system.particles
    particle = window.particle_system.particles[0]
    assert particle.sprite_rect == (2, 4, 8, 16)
    assert appearance_key(particle) == ("sprite", "packs/core/fx/spark.png", (2, 4, 8, 16))
