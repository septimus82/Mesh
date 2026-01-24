from __future__ import annotations

import pytest

from engine.particles_core import ParticleData, ParticleSystem


def test_particles_curves_default_linear() -> None:
    system = ParticleSystem()
    particle = ParticleData(
        x=0.0,
        y=0.0,
        vx=0.0,
        vy=0.0,
        life=1.0,
        alpha0=0.0,
        alpha1=100.0,
        scale0=2.0,
        scale1=0.0,
    )
    system.spawn([particle])

    system.update(0.5)
    assert particle.alpha_now == pytest.approx(50.0, abs=1e-6)
    assert particle.scale_now == pytest.approx(1.0, abs=1e-6)
