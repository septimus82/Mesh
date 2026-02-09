from __future__ import annotations

from typing import Any

import engine.optional_arcade as optional_arcade
from engine.physics_model import Aabb
from engine import physics_runtime


class _Sprite:
    def __init__(self, x: float, y: float, w: float, h: float, sid: str = "") -> None:
        self.center_x = x
        self.center_y = y
        self.width = w
        self.height = h
        self.id = sid
        self.fake_id = int(sid.encode("utf-8")[0]) if sid else 0


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


def test_cache_rebuild_on_scene_switch() -> None:
    optional_arcade.arcade.check_for_collision_with_list = _fake_collision  # type: ignore[attr-defined]
    physics_runtime.reset_broadphase_cache()
    physics_runtime.set_broadphase_enabled(True)

    colliders_a = [_Sprite(0, 0, 2, 2, "a")]
    entity = _Sprite(0, 0, 2, 2)
    _move(entity, colliders_a)
    build_a = physics_runtime._BROADPHASE_CACHE.build_count
    # Different scene -> different key
    colliders_b = [_Sprite(0, 0, 2, 2, "b")]
    _move(entity, colliders_b)
    build_b = physics_runtime._BROADPHASE_CACHE.build_count
    assert build_b == build_a + 1


def test_cache_stable_with_same_key() -> None:
    optional_arcade.arcade.check_for_collision_with_list = _fake_collision  # type: ignore[attr-defined]
    physics_runtime.reset_broadphase_cache()
    physics_runtime.set_broadphase_enabled(True)

    colliders = [_Sprite(0, 0, 2, 2, "a")]
    entity = _Sprite(0, 0, 2, 2)
    _move(entity, colliders)
    build1 = physics_runtime._BROADPHASE_CACHE.build_count
    _move(entity, colliders)
    build2 = physics_runtime._BROADPHASE_CACHE.build_count
    assert build2 == build1


def test_cache_rebuild_on_collider_change() -> None:
    optional_arcade.arcade.check_for_collision_with_list = _fake_collision  # type: ignore[attr-defined]
    physics_runtime.reset_broadphase_cache()
    physics_runtime.set_broadphase_enabled(True)

    colliders = [_Sprite(0, 0, 2, 2, "a")]
    entity = _Sprite(0, 0, 2, 2)
    _move(entity, colliders)
    build1 = physics_runtime._BROADPHASE_CACHE.build_count
    # Add collider -> key changes
    colliders.append(_Sprite(10, 0, 2, 2, "b"))
    _move(entity, colliders)
    build2 = physics_runtime._BROADPHASE_CACHE.build_count
    assert build2 == build1 + 1
