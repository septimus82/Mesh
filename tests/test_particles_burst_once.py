from __future__ import annotations

from engine.particles_core import BurstController


def test_particles_burst_once() -> None:
    burst = BurstController()
    assert burst.trigger(4) == 4
    assert burst.trigger(4) == 0
    assert burst.trigger(4, reset=True) == 4
    assert burst.trigger(4) == 0
