from __future__ import annotations

import pytest

from engine.particles_core import ParticleData, ParticleSystem


def test_particles_curves_scale() -> None:
    system = ParticleSystem()
    particle = ParticleData(
        x=0.0,
        y=0.0,
        vx=0.0,
        vy=0.0,
        life=1.0,
        scale0=1.0,
        scale1=0.0,
        scale_curve="ease_out",
    )
    system.spawn([particle])

    system.update(0.25)
    expected = (1.0 - 0.25) ** 2
    assert particle.scale_now == pytest.approx(expected, abs=1e-6)
    assert particle.scale_now < 0.75
