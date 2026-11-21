"""SL-1: DamageOnTouch reduces the touched target's Health (once per hit, honouring the cooldown).

Real runtime: a hidden GameWindow (tests/_b01_arena.py), the production DamageOnTouch + Health behaviours. Before
the fix DamageOnTouch only called ``window.on_damage`` (a signal + particles), so a touched player kept full HP.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import pytest

from engine import optional_arcade
from tests._b01_arena import PIC, Arena, close_window, hero, hp_of, make_window

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]


DAMAGE = 5  # the player's defence (engine rule, as for Hitbox/Projectile) is subtracted from it


def _trap(**cfg: Any) -> dict[str, Any]:
    config = {"target_name": "Hero", "damage": DAMAGE, "cooldown": 1, **cfg}
    return {"id": "trap", "name": "Trap", "x": 50, "y": 50, "sprite": PIC, "layer": "entities",
            "behaviours": ["DamageOnTouch"], "behaviour_config": {"DamageOnTouch": config}}


def _arena(tmp_path: Path, *entities: dict[str, Any]) -> tuple[Any, Arena]:
    window = make_window()
    arena = Arena(window, tmp_path)
    arena.write_room(*entities)
    arena.enter()
    return window, arena


@pytest.fixture()
def hurt(tmp_path: Path) -> Iterator[tuple[Arena, list[Any]]]:
    window, arena = _arena(tmp_path, hero(), _trap())
    events: list[Any] = []
    window.event_bus.subscribe("damage_applied", events.append)
    try:
        yield arena, events
    finally:
        close_window(window)


def _drop(arena: Arena) -> float:
    return float(DAMAGE) - float(arena.window.game_state_controller.get_player_stats().get("defense", 0))


def _touch(arena: Arena, dt: float = 0.1) -> None:
    next(b for b in arena.by_id("trap").mesh_behaviours_runtime if type(b).__name__ == "DamageOnTouch").update(dt)


def test_touch_reduces_health_once_per_hit_and_honours_cooldown(hurt: tuple[Arena, list[Any]]) -> None:
    arena, events = hurt
    player = arena.by_id("hero")
    _touch(arena)
    drop = _drop(arena)
    assert drop > 0
    assert hp_of(player) == 10 - drop
    assert len(events) == 1
    _touch(arena)  # still cooling down
    assert hp_of(player) == 10 - drop and len(events) == 1
    _touch(arena, 1.0)  # cooldown elapsed
    assert hp_of(player) == 10 - 2 * drop and len(events) == 2
    assert events[0].payload["target"] == "Hero" and events[0].payload["amount"] == drop


def test_invulnerable_target_takes_no_damage(hurt: tuple[Arena, list[Any]]) -> None:
    arena, _ = hurt
    next(b for b in arena.by_id("hero").mesh_behaviours_runtime if type(b).__name__ == "Health").invulnerable = True
    _touch(arena)
    assert hp_of(arena.by_id("hero")) == 10


def test_target_without_health_still_gets_the_event(tmp_path: Path) -> None:
    bare = {"id": "hero", "name": "Hero", "x": 50, "y": 50, "sprite": PIC, "layer": "entities"}
    window, arena = _arena(tmp_path, bare, _trap())
    try:
        events: list[Any] = []
        window.event_bus.subscribe("damage_applied", events.append)
        _touch(arena)
        assert len(events) == 1
    finally:
        close_window(window)
