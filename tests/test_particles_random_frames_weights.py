from __future__ import annotations

import pytest

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


def test_particles_random_frames_weights_invalid() -> None:
    window = _StubWindow()
    entity = _StubEntity()
    with pytest.raises(ValueError):
        ParticleEmitter(
            entity,
            window,
            mode="burst",
            count=1,
            seed="5",
            sprite="packs/core/fx/spark.png",
            frame_weights={"0": 0},
            frame_size=[8, 8],
            grid_cols=4,
        )
