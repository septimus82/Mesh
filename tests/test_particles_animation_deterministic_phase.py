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


def _spawn_phase_offsets(seed: int) -> list[int]:
    window = _StubWindow()
    entity = _StubEntity()
    emitter = ParticleEmitter(
        entity,
        window,
        mode="burst",
        count=5,
        seed=str(seed),
        sprite="packs/core/fx/spark.png",
        anim_frames=[0, 1, 2],
        anim_fps=12,
        anim_phase="random",
        frame_size=[16, 16],
        grid_cols=4,
    )
    emitter.update(1.0 / 60.0)
    return [p.anim_phase_offset for p in window.particle_system.particles]


def test_particles_animation_deterministic_phase() -> None:
    first = _spawn_phase_offsets(1234)
    second = _spawn_phase_offsets(1234)
    assert first == second
