from __future__ import annotations

from typing import Any

import engine.optional_arcade as optional_arcade
from engine import physics_runtime
from engine.physics_model import Aabb


class _MutableSprite:
    def __init__(self, x: float, y: float, w: float, h: float, sid: int) -> None:
        self.center_x = x
        self.center_y = y
        self.width = w
        self.height = h
        self.fake_id = sid

    @property
    def left(self) -> float:
        return self.center_x - self.width / 2.0

    @property
    def right(self) -> float:
        return self.center_x + self.width / 2.0

    @property
    def bottom(self) -> float:
        return self.center_y - self.height / 2.0

    @property
    def top(self) -> float:
        return self.center_y + self.height / 2.0


def _fake_collision(proxy: Any, sprites: list[Any]) -> list[Any]:
    proxy_aabb = Aabb(proxy.center_x, proxy.center_y, proxy.width, proxy.height)
    hits: list[Any] = []
    for s in sprites:
        s_aabb = Aabb(s.center_x, s.center_y, s.width, s.height)
        if proxy_aabb.intersection(s_aabb) is not None:
            hits.append(s)
    return hits


def _move(entity: Any, colliders: list[Any]) -> None:
    physics_runtime.move_entity_with_physics(entity, (1, 0), colliders)


def test_cache_rebuild_on_in_place_collider_mutation(monkeypatch) -> None:
    monkeypatch.setattr(
        optional_arcade.arcade,
        "check_for_collision_with_list",
        _fake_collision,
    )
    physics_runtime.reset_broadphase_cache()
    physics_runtime.set_broadphase_enabled(True)

    collider = _MutableSprite(0, 0, 2, 2, 1)
    entity = _MutableSprite(0, 0, 2, 2, 2)
    colliders = [collider]

    _move(entity, colliders)
    build1 = physics_runtime._BROADPHASE_CACHE.build_count

    collider.width = 3.0  # mutate in place (same list, same id/count)
    _move(entity, colliders)
    build2 = physics_runtime._BROADPHASE_CACHE.build_count

    assert build2 == build1 + 1
