from __future__ import annotations

from engine.particles_core import ParticleData, ParticleSystem


def test_particles_animation_no_loop_clamp() -> None:
    system = ParticleSystem()
    particle = ParticleData(
        x=0.0,
        y=0.0,
        vx=0.0,
        vy=0.0,
        life=2.0,
        sprite_path="packs/core/fx/spark.png",
        anim_frames=(0, 1, 2),
        anim_fps=10.0,
        anim_loop=False,
        frame_size=(8, 8),
        grid_cols=4,
    )
    system.spawn([particle])

    system.update(0.6)
    assert particle.sprite_rect == (16, 0, 8, 8)
