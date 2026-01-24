from __future__ import annotations

from engine.behaviours.particle_emitter import ParticleEmitter
from engine.particles_core import ParticleSystem


class _StubWindow:
    def __init__(self) -> None:
        self.particle_system = ParticleSystem()


class _StubEntity:
    def __init__(self) -> None:
        self.center_x = 3.0
        self.center_y = 4.0
        self.mesh_entity_data = {}


def test_particles_random_frames_range() -> None:
    window = _StubWindow()
    entity = _StubEntity()
    emitter = ParticleEmitter(
        entity,
        window,
        mode="burst",
        count=12,
        seed="77",
        sprite="packs/core/fx/spark.png",
        frame_range=[2, 5],
        frame_size=[8, 8],
        grid_cols=4,
    )
    emitter.update(1.0 / 60.0)

    rects = [p.sprite_rect for p in window.particle_system.particles]
    expected = {
        (16, 0, 8, 8),
        (24, 0, 8, 8),
        (0, 8, 8, 8),
        (8, 8, 8, 8),
    }
    assert all(rect in expected for rect in rects)
