from __future__ import annotations

from engine.particles_core import ParticleData, ParticleSystem


def test_particles_animation_progression() -> None:
    system = ParticleSystem()
    particle = ParticleData(
        x=0.0,
        y=0.0,
        vx=0.0,
        vy=0.0,
        life=1.0,
        sprite_path="packs/core/fx/spark.png",
        anim_frames=(0, 1, 2, 3),
        anim_fps=10.0,
        anim_loop=True,
        frame_size=(16, 16),
        grid_cols=4,
    )
    system.spawn([particle])

    system.update(0.05)
    assert particle.sprite_rect == (0, 0, 16, 16)

    system.update(0.05)
    assert particle.sprite_rect == (16, 0, 16, 16)

    system.update(0.1)
    assert particle.sprite_rect == (32, 0, 16, 16)
