from __future__ import annotations

from typing import Iterable

from engine.particles import ParticleManager


class _StubWindow:
    def __init__(self, seed: int | None) -> None:
        self.particle_seed = seed


def _snapshot_particles(particles: Iterable[object]) -> list[tuple[object, ...]]:
    snap: list[tuple[object, ...]] = []
    for p in particles:
        snap.append(
            (
                getattr(p, "x", None),
                getattr(p, "y", None),
                getattr(p, "vx", None),
                getattr(p, "vy", None),
                getattr(p, "life", None),
                getattr(p, "scale0", None),
                getattr(p, "scale1", None),
                getattr(p, "alpha0", None),
                getattr(p, "alpha1", None),
                getattr(p, "color", None),
                getattr(p, "shape", None),
                getattr(p, "size", None),
            )
        )
    return snap


def test_particle_effects_deterministic_with_seed() -> None:
    window_a = _StubWindow(seed=123)
    window_b = _StubWindow(seed=123)

    manager_a = ParticleManager(window_a)  # headless-safe
    manager_b = ParticleManager(window_b)

    manager_a.emit_hit_effect(10.0, 20.0)
    manager_b.emit_hit_effect(10.0, 20.0)
    assert _snapshot_particles(manager_a.system.particles) == _snapshot_particles(manager_b.system.particles)

    manager_a.emit_collect_effect(5.0, 7.0)
    manager_b.emit_collect_effect(5.0, 7.0)
    assert _snapshot_particles(manager_a.system.particles) == _snapshot_particles(manager_b.system.particles)
