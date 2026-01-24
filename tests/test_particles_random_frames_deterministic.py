from __future__ import annotations

from engine.behaviours.particle_emitter import ParticleEmitter
from engine.particles_core import ParticleSystem


class _StubWindow:
    def __init__(self) -> None:
        self.particle_system = ParticleSystem()


class _StubEntity:
    def __init__(self) -> None:
        self.center_x = 1.0
        self.center_y = 2.0
        self.mesh_entity_data = {}


def _run_spawn(seed: int) -> list[tuple[int, int, int, int]]:
    window = _StubWindow()
    entity = _StubEntity()
    emitter = ParticleEmitter(
        entity,
        window,
        mode="burst",
        count=6,
        seed=str(seed),
        sprite="packs/core/fx/spark.png",
        frames=[0, 1, 2, 3],
        frame_size=[16, 16],
        grid_cols=4,
    )
    emitter.update(1.0 / 60.0)
    return [p.sprite_rect for p in window.particle_system.particles]


def test_particles_random_frames_deterministic() -> None:
    first = _run_spawn(1234)
    second = _run_spawn(1234)
    assert first == second
