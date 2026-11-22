"""N3: one attack input is at most one ``input_attack`` combat_attack trace (Ember Hollow vertical slice).

Real runtime: a hidden GameWindow, the shipped player (PlayerController + Combat), the game's own ``attack`` key
(on_key_press/on_key_release, then frames). The trace used to be emitted every frame the key was held and even when
the Combat cooldown refused the swing, so one tap logged several ``input_attack`` events for one swing.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import pytest

from engine import optional_arcade
from tests._b01_arena import PIC, Arena, close_window, goblin, make_window

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

DT = 1 / 60
HERO = {"id": "hero", "name": "Hero", "tag": "player", "x": 50, "y": 50, "sprite": PIC,
        "behaviours": ["Health", "PlayerController", "Combat"],
        "behaviour_config": {"Health": {"max_hp": 10, "hp": 10},
                             "Combat": {"damage": 5, "cooldown": 1.0, "range": 40}}}


@pytest.fixture()
def arena(tmp_path: Path) -> Iterator[Arena]:
    window = make_window()
    try:
        a = Arena(window, tmp_path)
        enemy = goblin("g1", 82, 50)
        enemy["tag"] = "enemy"
        a.write_room(HERO, enemy)
        a.enter()
        menu = getattr(window, "main_menu_overlay", None)
        if menu is not None and menu.visible:
            menu.close()  # (a fresh window opens on the main menu, which blocks the player's input)
        yield a
    finally:
        close_window(window)


def _traces(arena: Arena) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []
    arena.window.event_bus.subscribe("combat_attack", lambda e: seen.append(dict(e.payload)))
    return seen


def _tap(arena: Arena, frames: int) -> None:
    key = optional_arcade.arcade.key.SPACE
    arena.window.on_key_press(key, 0)
    for _ in range(frames):
        arena.window.on_update(DT)
    arena.window.on_key_release(key, 0)
    arena.window.on_update(DT)


def _input_attacks(seen: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [p for p in seen if p.get("type") == "input_attack"]


def test_one_tap_is_one_input_attack_trace(arena: Arena) -> None:
    seen = _traces(arena)
    _tap(arena, frames=5)  # (a tap spans several frames)
    assert len(_input_attacks(seen)) == 1


def test_a_press_refused_by_the_cooldown_traces_nothing(arena: Arena) -> None:
    seen = _traces(arena)
    _tap(arena, frames=1)
    assert len(_input_attacks(seen)) == 1
    _tap(arena, frames=3)  # (well inside the 1 s cooldown: Combat refuses the swing)
    assert len(_input_attacks(seen)) == 1


def test_a_successful_swing_still_hits_once(arena: Arena) -> None:
    seen = _traces(arena)
    enemy = arena.by_id("g1")
    hp = next(b for b in enemy.mesh_behaviours_runtime if type(b).__name__ == "Health")
    _tap(arena, frames=5)
    assert hp.hp == 20 - 5
    assert len([p for p in seen if p.get("type") == "melee"]) == 1
