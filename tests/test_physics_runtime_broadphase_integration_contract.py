from __future__ import annotations

from typing import Any

import engine.optional_arcade as optional_arcade
from engine import physics_runtime
from engine.physics_model import Aabb


class _Sprite:
    def __init__(self, x: float, y: float, w: float, h: float) -> None:
        self.center_x = x
        self.center_y = y
        self.width = w
        self.height = h


def _intersects(a: Aabb, b: Aabb) -> bool:
    return a.intersection(b) is not None


def _fake_collision(proxy: Any, sprites: list[Any]) -> list[Any]:
    proxy_aabb = Aabb(proxy.center_x, proxy.center_y, proxy.width, proxy.height)
    hits: list[Any] = []
    for s in sprites:
        s_aabb = Aabb(s.center_x, s.center_y, s.width, s.height)
        if _intersects(proxy_aabb, s_aabb):
            hits.append(s)
    return hits


def _run_move(entity: Any, delta: tuple[float, float], colliders: list[Any]) -> tuple[float, float]:
    result = physics_runtime.move_entity_with_physics(entity, delta, colliders)
    return result.final_pos


def test_broadphase_matches_baseline(monkeypatch) -> None:
    colliders = [
        _Sprite(10, 0, 2, 2),  # right wall
        _Sprite(0, 10, 2, 2),  # top wall
        _Sprite(10, 10, 2, 2),  # corner
    ]
    entity = _Sprite(0, 0, 2, 2)

    monkeypatch.setattr(
        optional_arcade.arcade,
        "check_for_collision_with_list",
        _fake_collision,
    )

    physics_runtime.set_broadphase_enabled(False)
    baseline = _run_move(entity, (15, 15), colliders)

    # Reset entity
    entity = _Sprite(0, 0, 2, 2)
    physics_runtime.set_broadphase_enabled(True)
    physics_runtime.reset_broadphase_cache()
    broad = _run_move(entity, (15, 15), colliders)

    assert broad == baseline


def test_broadphase_candidate_reduction_and_counters(monkeypatch) -> None:
    colliders = [_Sprite(x * 20, 0, 2, 2) for x in range(200)]
    entity = _Sprite(0, 0, 2, 2)
    monkeypatch.setattr(
        optional_arcade.arcade,
        "check_for_collision_with_list",
        _fake_collision,
    )

    physics_runtime.set_broadphase_enabled(True)
    physics_runtime.reset_broadphase_cache()
    physics_runtime.enable_broadphase_counters(True)

    _run_move(entity, (1, 0), colliders)

    # Expect fewer candidates than total
    assert physics_runtime._BROADPHASE_CACHE.candidate_count <= len(colliders)
    assert physics_runtime._BROADPHASE_CACHE.exact_checks_count <= len(colliders)
    assert physics_runtime._BROADPHASE_CACHE.candidate_count < len(colliders)
    assert physics_runtime._BROADPHASE_CACHE.candidate_count == 2
    assert physics_runtime._BROADPHASE_CACHE.exact_checks_count == 2

    stats = physics_runtime.get_broadphase_stats()
    assert stats.get("candidate_count") == 2
    assert stats.get("exact_checks_count") == 2

    physics_runtime.reset_broadphase_counters()
    stats_after = physics_runtime.get_broadphase_stats()
    assert stats_after.get("candidate_count") == 0
    assert stats_after.get("exact_checks_count") == 0
