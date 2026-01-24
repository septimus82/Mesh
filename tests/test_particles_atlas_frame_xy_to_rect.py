from __future__ import annotations

from engine.behaviours.particle_emitter import ParticleEmitter
from engine.particles_core import ParticleSystem, appearance_key


class _StubWindow:
    def __init__(self) -> None:
        self.particle_system = ParticleSystem()


class _StubEntity:
    def __init__(self) -> None:
        self.center_x = 7.0
        self.center_y = 9.0
        self.mesh_entity_data = {}


def test_particles_atlas_frame_xy_to_rect() -> None:
    window = _StubWindow()
    entity = _StubEntity()
    emitter = ParticleEmitter(
        entity,
        window,
        mode="burst",
        count=1,
        sprite="packs/core/fx/spark.png",
        frame_xy=[2, 3],
        frame_size=[5, 7],
    )
    emitter.update(1.0 / 60.0)

    assert window.particle_system.particles
    particle = window.particle_system.particles[0]
    assert particle.sprite_rect == (10, 21, 5, 7)
    assert appearance_key(particle) == ("sprite", "packs/core/fx/spark.png", (10, 21, 5, 7))
