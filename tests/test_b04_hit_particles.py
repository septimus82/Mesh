"""B-04: damage makes hit particles appear at the damaged entity.

Real runtime: a hidden GameWindow (harness of tests/_b01_arena.py), the production Health behaviour and
scene controller ``on_damage``. The damage events carry the target's *name*; the handler must resolve it to the
sprite and burst at its position (and skip quietly when no sprite has that name).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import pytest

from engine import optional_arcade
from tests._b01_arena import Arena, close_window, goblin, hero, make_window

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]


@pytest.fixture()
def arena(tmp_path: Path) -> Iterator[Arena]:
    window = make_window()
    try:
        a = Arena(window, tmp_path)
        a.write_room(hero(), goblin("g1", 120, 80))
        a.enter()
        yield a
    finally:
        close_window(window)


def _spawned(arena: Arena) -> list[Any]:
    return list(arena.window.particle_manager.system.particles)


def _health(sprite: Any) -> Any:
    return next(b for b in sprite.mesh_behaviours_runtime if type(b).__name__ == "Health")


def test_health_damage_bursts_hit_particles_at_the_damaged_entity(arena: Arena) -> None:
    gob = arena.by_id("g1")
    assert _spawned(arena) == []
    _health(gob).apply_damage(3, source_entity="Hero")
    parts = _spawned(arena)
    assert len(parts) == 8
    assert {(round(p.x), round(p.y)) for p in parts} == {(120, 80)}


def test_scene_controller_on_damage_bursts_at_the_target(arena: Arena) -> None:
    arena.controller.on_damage(arena.by_id("hero"), arena.by_id("g1"), 2)
    assert {(round(p.x), round(p.y)) for p in _spawned(arena)} == {(120, 80)}


def test_damage_to_a_name_with_no_sprite_spawns_nothing_and_does_not_raise(arena: Arena) -> None:
    arena.window.emit_signal("damage_applied", source="Hero", target="Nobody", amount=1.0)
    assert _spawned(arena) == []
