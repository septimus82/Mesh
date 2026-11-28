"""N1 (Ember Hollow): the player's HP carries across room changes made through a door.

Before the fix every room change rebuilt the player from the new room's data, so HP 7 became full HP at the door.
Real hidden GameWindow, real scene files, the production SceneTransition / queue_scene_change paths and SaveManager.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import pytest

from engine import optional_arcade
from engine.scene_lifecycle_controller import handle_pending_scene_change, handle_pending_scene_load
from tests._b01_arena import Arena, close_window, goblin, hero, hp_of, make_window, set_hp

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]


@pytest.fixture()
def arena(tmp_path: Path) -> Iterator[Arena]:
    window = make_window()
    try:
        yield Arena(window, tmp_path)
    finally:
        close_window(window)


def _two_rooms(arena: Arena) -> Path:
    other = arena.root / "hollow.json"
    other.write_text(json.dumps({"name": "Hollow", "schema_version": 1, "version": 1, "layers": [],
                                 "entities": [hero(), goblin("gob", 200, 200)]}), encoding="utf-8")
    door = {"id": "door", "name": "Door", "x": 80, "y": 50, "sprite": "assets/placeholder.png",
            "behaviours": ["SceneTransition"],
            "behaviour_config": {"SceneTransition": {"target_scene": str(other)}}}
    arena.write_room(hero(), door)
    arena.enter()
    return other


def _player(arena: Arena) -> Any:
    return arena.by_id("hero")


def _walk_through_door(arena: Arena) -> None:
    door = arena.by_id("door")
    behaviour = next(b for b in door.mesh_behaviours_runtime if type(b).__name__ == "SceneTransition")
    behaviour._trigger_transition(reason="test")
    assert handle_pending_scene_load(arena.controller) is True


def test_a_door_keeps_the_players_hp(arena: Arena) -> None:
    other = _two_rooms(arena)
    set_hp(_player(arena), 7)
    _walk_through_door(arena)
    assert arena.controller.current_scene_path == str(other)
    assert hp_of(_player(arena)) == 7


def test_a_queued_scene_change_keeps_the_players_hp(arena: Arena) -> None:
    other = _two_rooms(arena)
    set_hp(_player(arena), 4)
    arena.window.queue_scene_change(str(other))
    assert handle_pending_scene_change(arena.controller) is True
    assert hp_of(_player(arena)) == 4


def test_only_the_player_is_carried_and_a_new_game_starts_full(arena: Arena) -> None:
    other = _two_rooms(arena)
    set_hp(_player(arena), 7)
    _walk_through_door(arena)
    assert hp_of(arena.by_id("gob")) == 20  # the enemy's Health is its own room's
    # a new game (a plain scene load, not a door) is a fresh player
    set_hp(_player(arena), 3)
    arena.controller.load_scene(str(arena.room))
    assert hp_of(_player(arena)) == 10
    assert other.exists()


def test_a_saved_hp_wins_on_load(arena: Arena) -> None:
    _two_rooms(arena)
    set_hp(_player(arena), 6)
    arena.save()
    set_hp(_player(arena), 9)
    _walk_through_door(arena)  # carries 9 into the Hollow
    assert arena.load()
    assert hp_of(_player(arena)) == 6


def test_a_loaded_game_does_not_inherit_hp_from_the_room_left_behind(arena: Arena) -> None:
    _two_rooms(arena)
    set_hp(_player(arena), 8)
    arena.save()
    set_hp(_player(arena), 2)
    arena.window.request_scene_change(str(arena.room))  # a menu / Continue style change, not a door
    assert handle_pending_scene_load(arena.controller) is True
    assert hp_of(_player(arena)) == 10


def test_a_door_that_never_happened_leaves_no_mark_for_the_next_load(arena: Arena) -> None:
    _two_rooms(arena)
    set_hp(_player(arena), 7)
    arena.controller._carry_player_hp = True  # as a door sets it, then the room change never comes
    arena.window.request_scene_change(str(arena.room))  # New Game / Continue / menu
    assert handle_pending_scene_load(arena.controller) is True
    assert hp_of(_player(arena)) == 10
    arena.controller._carry_player_hp = True
    arena.controller.request_scene_reload()
    assert handle_pending_scene_load(arena.controller) is True
    assert hp_of(_player(arena)) == 10
