from __future__ import annotations

import pytest

from engine.particles_core import ParticleData, ParticleSystem


def _curve(kind: str, t: float) -> float:
    if kind == "linear":
        return t
    if kind == "ease_in":
        return t * t
    if kind == "ease_out":
        return 1.0 - (1.0 - t) * (1.0 - t)
    if kind == "ease_in_out":
        if t < 0.5:
            return 2.0 * t * t
        return 1.0 - 2.0 * (1.0 - t) * (1.0 - t)
    raise AssertionError(f"unknown curve {kind}")


@pytest.mark.parametrize("curve", ["linear", "ease_in", "ease_out", "ease_in_out"])
def test_particles_curves_alpha(curve: str) -> None:
    system = ParticleSystem()
    particle = ParticleData(
        x=0.0,
        y=0.0,
        vx=0.0,
        vy=0.0,
        life=1.0,
        alpha0=0.0,
        alpha1=255.0,
        alpha_curve=curve,
    )
    system.spawn([particle])

    for t in (0.25, 0.5, 0.75):
        system.update(0.25)
        expected = 255.0 * _curve(curve, t)
        assert particle.alpha_now == pytest.approx(expected, abs=1e-4)
