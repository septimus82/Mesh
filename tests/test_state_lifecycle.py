"""Runtime state across a game's transitions (#422): a fresh game, New Game, loading a save, rooms in and out.

The contract checked here, with a real hidden GameWindow and real scene files:
- A room's objects listen to the game's events only while the room is loaded. Every scene load used to add each
  behaviour's event-bus listeners again without removing the last room's, so one event counted once per visit.
- What a room remembers (objects collected or defeated) belongs to the game that loaded it. New Game, and Studio's
  Play and Stop, reset the game state and then load a room, and the load used to write the old game's room memory
  into the new game's state, so a collected coin stayed gone in the new game.
- A new game isn't over: ``replace_state`` used to leave ``game_over`` set, so the next game began on the
  game-over screen.
- Kept as they were: leaving a room still remembers what was collected; window-level listeners stay; loading a save
  replaces flags, counters and values, with nothing left from the game that was running.

Studio's repeated Play / Stop is tests/test_state_lifecycle_gpu.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import pytest

import engine.optional_arcade as optional_arcade
from engine.config import EngineConfig
from engine.save_manager import SaveManager
from tests._game_window_live import dispose_game_window

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

PICTURE = "assets/placeholder.png"
HERO = {"id": "hero", "name": "Hero", "tag": "player", "x": 100, "y": 100, "sprite": PICTURE,
        "behaviours": ["PlayerController"]}
PINGER = {"id": "pinger", "name": "Pinger", "x": 200, "y": 160, "sprite": PICTURE,
          "behaviours": ["IncrementCounterOnEvent"],
          "behaviour_config": {"IncrementCounterOnEvent": {"event_type": "ping", "counter": "pings"}}}
COIN = {"id": "coin", "name": "Coin", "x": 140, "y": 100, "sprite": PICTURE}


def _scene(name: str, *entities: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "schema_version": 1, "version": 1, "layers": [], "entities": list(entities)}


@pytest.fixture()
def game(tmp_path: Path) -> Iterator[tuple[Any, str, str]]:
    """A game with two rooms: the Yard (a Pinger counting "ping" events, a Coin) and the Shed (nothing to count)."""
    from engine.game import GameWindow

    yard, shed = tmp_path / "yard.json", tmp_path / "shed.json"
    yard.write_text(json.dumps(_scene("Yard", HERO, PINGER, COIN)), encoding="utf-8")
    shed.write_text(json.dumps(_scene("Shed", HERO)), encoding="utf-8")
    cfg = EngineConfig(width=320, height=200, title="State lifecycle", vsync=False, start_scene="", world_file=None,
                       main_menu_scene=None)
    window = GameWindow(width=320, height=200, title=cfg.title, vsync=False, config=cfg)
    window.save_manager = SaveManager(window, save_dir=tmp_path / "saves")
    try:
        window.scene_controller.load_scene(str(yard))
        yield window, str(yard), str(shed)
    finally:
        dispose_game_window(window)


def _listeners(window: Any, event: str) -> int:
    return len(window.event_bus._subscribers.get(event, []))


def _names(window: Any) -> set[str]:
    return {getattr(s, "mesh_name", "") for s in window.scene_controller.all_sprites}


def _collect_coin(window: Any) -> None:
    next(s for s in window.scene_controller.all_sprites if s.mesh_name == "Coin").remove_from_sprite_lists()


# --------------------------------------------------------------------- a room's listeners end with it

def test_a_rooms_objects_stop_listening_when_it_is_left(game: tuple[Any, str, str]) -> None:
    window, yard, shed = game
    for _ in range(3):
        window.scene_controller.load_scene(shed)
        assert _listeners(window, "ping") == 0  # (the Yard's Pinger is gone, and so is its listener)
        window.scene_controller.load_scene(yard)
    assert _listeners(window, "ping") == 1
    window.emit_signal("ping")
    assert window.game_state_controller.state.counters.get("pings") == 1.0  # (once, not once per visit)


def test_rebuilding_an_objects_behaviours_replaces_its_listeners(game: tuple[Any, str, str]) -> None:
    window, _yard, _shed = game
    pinger = next(s for s in window.scene_controller.all_sprites if s.mesh_name == "Pinger")
    for _ in range(3):  # (as a live edit of the object does)
        window.scene_controller._rebuild_behaviours_for_sprite(pinger)
    assert _listeners(window, "ping") == 1
    window.emit_signal("ping")
    assert window.game_state_controller.state.counters.get("pings") == 1.0


def test_the_games_own_listeners_stay_through_room_changes(game: tuple[Any, str, str]) -> None:
    window, yard, shed = game
    before = {kind: len(listeners) for kind, listeners in window.event_bus._subscribers.items() if kind != "ping"}
    wildcards = len(window.event_bus._wildcard_subscribers)
    for path in (shed, yard, shed, yard):
        window.scene_controller.load_scene(path)
    after = {kind: len(listeners) for kind, listeners in window.event_bus._subscribers.items() if kind != "ping"}
    assert after == before and len(window.event_bus._wildcard_subscribers) == wildcards


# --------------------------------------------------------------------- room memory belongs to its game

def test_leaving_a_room_still_remembers_what_was_collected_there(game: tuple[Any, str, str]) -> None:
    window, yard, shed = game
    _collect_coin(window)
    window.scene_controller.load_scene(shed)
    window.scene_controller.load_scene(yard)
    assert "Coin" not in _names(window)
    memory = window.game_state_controller.get_var("room_memory")
    assert memory and list(memory.values())[0] == {"removed": ["coin"]}


def test_a_new_game_doesnt_inherit_the_old_games_room_memory(game: tuple[Any, str, str]) -> None:
    window, yard, _shed = game
    _collect_coin(window)
    window.game_state_controller.replace_state({})  # (New Game, Studio's Play and Stop: a new game ...)
    window.scene_controller.load_scene(yard)  # (... then its room)
    assert "Coin" in _names(window)
    assert window.game_state_controller.get_var("room_memory") is None


# --------------------------------------------------------------------- a new game isn't over

def test_a_new_game_is_not_over(game: tuple[Any, str, str]) -> None:
    window, _yard, _shed = game
    window.game_over, window.paused = True, True  # (the player died)
    window.game_over_screen.visible = True
    window.game_state_controller.replace_state({})
    assert (window.game_over, window.game_over_screen.visible, window.paused) == (False, False, False)


def test_a_new_game_leaves_a_pause_that_isnt_a_game_over_alone(game: tuple[Any, str, str]) -> None:
    window, _yard, _shed = game
    window.paused = True  # (a menu has the game paused: whoever opened it decides)
    window.game_state_controller.replace_state({})
    assert window.paused is True and window.game_over is False


# --------------------------------------------------------------------- loading a save

def test_loading_a_save_brings_back_its_state_and_nothing_of_the_running_game(game: tuple[Any, str, str]) -> None:
    window, _yard, shed = game
    controller = window.game_state_controller
    window.set_flag("met_the_guide", True)
    controller.add_counter("coins", 3)
    controller.set_var("chest_opened", True)
    assert window.save_manager.save_game("slot")
    saved = controller.export_state()
    window.set_flag("later_flag", True)  # (the game goes on after the save)
    controller.add_counter("coins", 10)
    controller.add_counter("later_counter", 1)
    controller.set_var("later_value", "x")
    window.scene_controller.load_scene(shed)
    assert window.save_manager.load_game("slot")
    loaded = controller.export_state()
    assert loaded["flags"] == saved["flags"] and loaded["counters"] == saved["counters"]
    assert "later_value" not in loaded["variables"] and loaded["variables"].get("chest_opened") is True
