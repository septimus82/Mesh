from __future__ import annotations

from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from engine import physics_runtime
from engine.physics_model import Aabb, Circle, circle_aabb_overlap, circle_circle_overlap

pytestmark = [pytest.mark.fast]


def test_circle_circle_overlap_boundary_conditions() -> None:
    assert circle_circle_overlap((0.0, 0.0), 1.0, (1.9, 0.0), 1.0) is True
    assert circle_circle_overlap((0.0, 0.0), 1.0, (2.0, 0.0), 1.0) is False
    assert circle_circle_overlap((0.0, 0.0), 1.0, (2.1, 0.0), 1.0) is False


def test_circle_aabb_overlap_boundary_conditions() -> None:
    box = Aabb(0.0, 0.0, 2.0, 2.0)
    assert circle_aabb_overlap((1.9, 0.0), 1.0, box) is True
    assert circle_aabb_overlap((2.0, 0.0), 1.0, box) is False
    assert circle_aabb_overlap((0.0, 0.0), 0.25, box) is True


def test_circle_broadphase_bounds_are_correct() -> None:
    circle = Circle(5.0, 6.0, 3.0)
    bounds = circle.bounds()
    assert bounds.x == pytest.approx(5.0)
    assert bounds.y == pytest.approx(6.0)
    assert bounds.w == pytest.approx(6.0)
    assert bounds.h == pytest.approx(6.0)

    sprite = type(
        "CircleSprite",
        (),
        {
            "center_x": 5.0,
            "center_y": 6.0,
            "width": 10.0,
            "height": 10.0,
            "collider_kind": "circle",
            "collider_radius": 3.0,
        },
    )()
    runtime_bounds = physics_runtime._sprite_to_aabb(sprite)
    assert runtime_bounds == Aabb(5.0, 6.0, 6.0, 6.0)


def test_circle_narrowphase_dispatch_used_when_circle_involved(monkeypatch: pytest.MonkeyPatch) -> None:
    entity = type("Entity", (), {"center_x": 0.0, "center_y": 0.0, "width": 2.0, "height": 2.0})()
    wall = type(
        "CircleWall",
        (),
        {
            "center_x": 8.0,
            "center_y": 0.0,
            "width": 4.0,
            "height": 4.0,
            "collider_kind": "circle",
            "collider_radius": 2.0,
        },
    )()

    def _should_not_be_called(_proxy: Any, _sprites: Any) -> list[Any]:
        raise AssertionError("Arcade AABB collision path should be bypassed when a circle collider is involved")

    monkeypatch.setattr(optional_arcade.arcade, "check_for_collision_with_list", _should_not_be_called)

    previous = physics_runtime.get_broadphase_stats().get("enabled", True)
    physics_runtime.set_broadphase_enabled(False)
    try:
        result = physics_runtime.move_entity_with_physics(entity, (8.0, 0.0), [wall])
    finally:
        physics_runtime.set_broadphase_enabled(bool(previous))

    assert result.hit_x is True
    assert result.final_pos[0] == pytest.approx(5.0)


def test_aabb_only_collision_behavior_unchanged_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    entity = type("Entity", (), {"center_x": 0.0, "center_y": 0.0, "width": 10.0, "height": 10.0})()
    wall = type("Wall", (), {"center_x": 20.0, "center_y": 0.0, "width": 10.0, "height": 100.0})()
    calls = {"n": 0}

    def _aabb_collision(proxy: Any, sprites: Any) -> list[Any]:
        calls["n"] += 1
        proxy_aabb = Aabb(proxy.center_x, proxy.center_y, proxy.width, proxy.height)
        hits: list[Any] = []
        for sprite in sprites:
            sprite_aabb = Aabb(sprite.center_x, sprite.center_y, sprite.width, sprite.height)
            if proxy_aabb.intersection(sprite_aabb) is not None:
                hits.append(sprite)
        return hits

    monkeypatch.setattr(optional_arcade.arcade, "check_for_collision_with_list", _aabb_collision)

    previous = physics_runtime.get_broadphase_stats().get("enabled", True)
    physics_runtime.set_broadphase_enabled(False)
    try:
        result = physics_runtime.move_entity_with_physics(entity, (20.0, 0.0), [wall])
    finally:
        physics_runtime.set_broadphase_enabled(bool(previous))

    assert calls["n"] >= 1
    assert result.hit_x is True
    assert result.final_pos == pytest.approx((10.0, 0.0))
