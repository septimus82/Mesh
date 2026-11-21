"""B-04b: picking up a collectible bursts collect particles where the item was.

Real runtime: a hidden GameWindow (harness of tests/_b01_arena.py), the production Collectible behaviour. The
pick-up event carries the item's position (the sprite is removed right after), which the handler must use.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest

from engine import optional_arcade
from tests._b01_arena import PIC, Arena, close_window, hero, make_window

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]


@pytest.fixture()
def arena(tmp_path: Path) -> Iterator[Arena]:
    window = make_window()
    try:
        a = Arena(window, tmp_path)
        coin = {"id": "coin", "name": "Coin", "x": 50, "y": 50, "sprite": PIC, "layer": "entities",
                "behaviours": ["Collectible"], "behaviour_config": {"Collectible": {"collect_by_name": "Hero"}}}
        a.write_room(hero(), coin)
        a.enter()
        yield a
    finally:
        close_window(window)


def _spawned(arena: Arena) -> list:
    return list(arena.window.particle_manager.system.particles)


def test_picking_up_a_collectible_bursts_collect_particles_at_its_position(arena: Arena) -> None:
    coin = arena.by_id("coin")
    assert _spawned(arena) == []
    for b in coin.mesh_behaviours_runtime:
        if type(b).__name__ == "Collectible":
            b.update(0.016)
    assert coin not in arena.sprites()  # picked up and removed
    parts = _spawned(arena)
    assert len(parts) == 12
    assert {(round(p.x), round(p.y)) for p in parts} == {(50, 50)}


def test_a_pickup_event_without_a_position_spawns_nothing(arena: Arena) -> None:
    arena.window.emit_signal("collectible_picked", collectible_name="Ghost", collector="Hero")
    assert _spawned(arena) == []
