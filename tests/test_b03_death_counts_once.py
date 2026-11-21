"""B-03: one logical death is one counted outcome.

Real runtime: a hidden GameWindow, a real scene file, the production Health death path (damage to 0). The shipped
cellar quest ("rats_killed") counts deaths with IncrementCounterOnEvent("died", name filter); Health publishes "died"
on the legacy bus both for gameplay-style subscribers (payload name/entity) and for legacy ones (payload actor/name),
so a counter without an actor check counted each death twice.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import pytest

from engine import optional_arcade
from tests._b01_arena import PIC, Arena, close_window, make_window

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

HERO = {"id": "hero", "name": "Hero", "tag": "player", "x": 50, "y": 50, "sprite": PIC,
        "behaviours": ["Health"], "behaviour_config": {"Health": {"max_hp": 10, "hp": 10}}}


def _rat(eid: str, x: float) -> dict[str, Any]:
    return {"id": eid, "name": "Rat1", "tag": "enemy", "x": x, "y": 200, "sprite": PIC, "layer": "entities",
            "behaviours": ["Health", "GrantExperience"],
            "behaviour_config": {"Health": {"max_hp": 3, "hp": 3}, "GrantExperience": {"xp": 5}}}


# As scenes/cellar.json does: a logic entity counts the deaths by name.
LOGIC = {"id": "logic", "name": "QuestLogic", "x": 0, "y": 0, "sprite": PIC, "layer": "background",
         "behaviours": ["IncrementCounterOnEvent"],
         "behaviour_config": {"IncrementCounterOnEvent": {"event_type": "died", "counter": "rats_killed",
                                                          "payload_field": "name", "payload_value": "Rat1"}}}


@pytest.fixture()
def arena(tmp_path: Path) -> Iterator[Arena]:
    window = make_window()
    try:
        yield Arena(window, tmp_path)
    finally:
        close_window(window)


def _health(sprite: Any) -> Any:
    return next(b for b in sprite.mesh_behaviours_runtime if type(b).__name__ == "Health")


def test_one_death_counts_once(arena: Arena) -> None:
    arena.write_room(HERO, LOGIC, _rat("rat_a", 200), _rat("rat_b", 260))
    arena.enter()
    window = arena.window
    seen: list[dict[str, Any]] = []
    window.event_bus.subscribe("died", lambda e: seen.append(dict(e.payload)))
    xp: list[Any] = []
    orig_xp = window.game_state_controller.add_xp
    window.game_state_controller.add_xp = lambda amount: (xp.append(amount), orig_xp(amount))[1]

    _health(arena.by_id("rat_a")).apply_damage(99)

    assert window.get_counter("rats_killed") == 1  # one death, one kill
    assert len(xp) == 1
    # one notification, with the legacy payload the actor-matching subscribers read
    assert len(seen) == 1 and seen[0]["name"] == "Rat1" and seen[0]["actor"] is not None

    _health(arena.by_id("rat_b")).apply_damage(99)
    assert window.get_counter("rats_killed") == 2
