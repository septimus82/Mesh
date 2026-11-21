"""B-08: a fast or hitched move can't skip a thin wall, and a non-finite move can't park an entity at NaN.

Real runtime: a hidden GameWindow (harness of tests/_b01_arena.py). One move longer than a wall plus the mover used to
be tested only at its destination, so the mover landed past the wall.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Iterator

import pytest

from engine import optional_arcade
from tests._b01_arena import PIC, Arena, close_window, hero, make_window

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

WALL = {"id": "wall", "name": "Wall", "x": 300, "y": 100, "sprite": PIC, "layer": "entities", "solid": True}


def _runner(*behaviours: tuple[str, dict[str, Any]], x: float = 100) -> dict[str, Any]:
    return {"id": "run", "name": "Runner", "x": x, "y": 100, "sprite": PIC, "layer": "entities",
            "behaviours": [n for n, _ in behaviours], "behaviour_config": {n: c for n, c in behaviours}}


@pytest.fixture()
def arena(tmp_path: Path) -> Iterator[Arena]:
    window = make_window()
    try:
        yield Arena(window, tmp_path)
    finally:
        close_window(window)


def _enter(arena: Arena, runner: dict[str, Any]) -> Any:
    arena.write_room(hero(), WALL, runner)
    arena.enter()
    return arena.by_id("run")


def test_legacy_mover_stops_at_a_thin_wall(arena: Arena) -> None:
    runner = _enter(arena, _runner())
    arena.window.move_entity_with_collision(runner, 400, 0)
    assert runner.right <= arena.by_id("wall").left + 1e-6


def test_physics_mover_stops_at_a_thin_wall(arena: Arena) -> None:
    from engine.physics_runtime import move_entity_with_physics

    runner = _enter(arena, _runner())
    result = move_entity_with_physics(runner, (400, 0), arena.controller.solid_sprites)
    assert result.hit_x
    assert runner.right <= arena.by_id("wall").left + 1e-6


def test_hitched_frame_does_not_carry_a_follower_through_the_wall(arena: Arena) -> None:
    runner = _enter(arena, _runner(("FollowTarget", {"follow_target": "Hero", "follow_speed": 3000}), x=150))
    arena.by_id("hero").center_x = 600
    arena.window.on_update(0.1)  # a 300 px step in one frame
    assert runner.right <= arena.by_id("wall").left + 1e-6


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_move_leaves_the_entity_where_it_is(arena: Arena, bad: float) -> None:
    from engine.physics_runtime import move_entity_with_physics

    runner = _enter(arena, _runner())
    arena.window.move_entity_with_collision(runner, bad, 0)
    arena.window.move_entity_with_collision(runner, 0, bad)
    move_entity_with_physics(runner, (bad, bad), arena.controller.solid_sprites)
    assert (runner.center_x, runner.center_y) == (100, 100)
