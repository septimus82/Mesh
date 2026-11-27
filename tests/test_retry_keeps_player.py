"""#750: retrying after the player dies brings the player back.

Room memory (engine.scene_runtime.room_memory) remembers the authored objects that left a room (collected, defeated)
and leaves them out when the room is built again. A dead player leaves its sprite lists too, and the game-over retry
(SPACE, engine/game_runtime/tick.py) reloads the room through ``load_scene``, which records what left first: the player
was remembered as removed, and the room came back without it (and so did every save made after).

The player is never remembered as removed now, and reads ignore a player id an older save recorded.

Checked with a real hidden GameWindow and a combat room like ``scenes/game1a_combat_room.json`` (an authored player
with Health, two enemies): the player dies through its Health, SPACE goes through the window's own key dispatch and
tick. What retry restores: the room as authored (the player at its authored place with its authored HP, game over
cleared), except what room memory keeps: an enemy defeated before the death stays defeated (room memory's design since
it exists; only the player is exempt). The same with the shared player (Project.player) in a room Studio made, whose
file has only a thin ``{"id", "x", "y", "prefab_id": "player"}`` for it.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from engine.scene_runtime import room_memory
from tests._real_game import HALL, PIC, RealGame, author, new_project, place, real_game

pytestmark = [pytest.mark.integration,  # (a generated project in a temporary folder; one hidden game window)
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

ARENA, COMMONS = "Arena", "Commons"  # its own player / the shared player (Studio's way)
PLAYER = "arena_player"
HOME = (96.0, 180.0)  # where the Arena has its player


def _entity(entity_id: str, name: str, x: float, y: float, tag: str, behaviours: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {"id": entity_id, "name": name, "tag": tag, "x": x, "y": y, "sprite": PIC, "layer": "entities",
            "behaviours": list(behaviours), "behaviour_config": behaviours}


def _arena_entities() -> list[dict[str, Any]]:
    """Like scenes/game1a_combat_room.json: an authored player with Health, two enemies (standing still here)."""
    enemy = {"Health": {"hp": 5, "max_hp": 5}}
    return [_entity(PLAYER, "Player", *HOME, "player", {"PlayerController": {}, "Health": {"hp": 20, "max_hp": 20}}),
            _entity("enemy_a", "Enemy A", 310, 180, "enemy", enemy),
            _entity("enemy_b", "Enemy B", 380, 180, "enemy", enemy)]


@pytest.fixture(scope="module")
def running(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RealGame]:
    base = tmp_path_factory.mktemp("retry")
    project = new_project(base / "game")
    key = project.add_room(ARENA)
    project.save()
    path = Path(project.root) / project.path(key)  # (its own player in place of the shared one: written as a file)
    scene = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**scene, "entities": _arena_entities()}, indent=2), encoding="utf-8")
    commons = project.add_room(COMMONS)
    (shared,) = project.shared_players(commons)
    health = {"op": "set_behaviour_param", "entity_id": shared, "behaviour": "Health"}
    author(project, commons, [{"op": "add_behaviour", "entity_id": shared, "behaviour": "Health"},
                              {**health, "param": "max_hp", "value": 12}, {**health, "param": "hp", "value": 12}])
    author(project, commons, place("Wolf", 300, 200, ("Health", {"max_hp": 5, "hp": 5})))
    thin = next(e for e in json.loads((Path(project.root) / project.path(commons)).read_text(encoding="utf-8"))["entities"]
                if e.get("id") == shared)
    assert set(thin) <= {"id", "x", "y", "elevation", "prefab_id"} and thin["prefab_id"] == "player"  # (as Studio stores it)
    launch = base / "elsewhere"
    launch.mkdir()
    with real_game(project, launch) as started:
        yield started


@pytest.fixture()
def game(running: RealGame) -> RealGame:
    """A new visit to the Arena: nothing remembered, not game over."""
    g = running.resume()
    g.window.game_over = g.window.paused = g.window.game_over_screen.visible = False
    g.enter(g.room(HALL))
    g.gs.set_var(room_memory.VAR, {})
    g.enter(g.room(ARENA))
    return g


def _arena(g: RealGame) -> str:
    return room_memory.room_key(g.path(g.room(ARENA)))


def _removed(g: RealGame) -> set[str]:
    return room_memory.removed_ids(g.window, _arena(g))


def _die(g: RealGame, enemy: str = "Enemy A") -> None:
    """An enemy is defeated, then the player dies: both through their Health, as a hit does."""
    g.behaviour(enemy, "Health").apply_damage(100, source_entity="Player")
    g.behaviour("Player", "Health").apply_damage(100, source_entity="Enemy B")
    g.frames(3)
    assert g.player() is None and g.window.game_over is True and g.window.game_over_screen.visible is True


def _retry(g: RealGame) -> None:
    g.key("SPACE")  # (game over: the tick reloads the room on SPACE)
    g.frames(3)


def _assert_playable(g: RealGame, home: tuple[float, float] = HOME, hp: float = 20) -> None:
    player = g.player()
    assert player is not None, "the room came back without the player"
    assert (player.center_x, player.center_y) == home
    health = next(b for b in player.mesh_behaviours_runtime if type(b).__name__ == "Health")
    assert (health.hp, health.max_hp, health._dead) == (hp, hp, False)
    window = g.window
    assert window.game_over is False and window.game_over_screen.visible is False and window.paused is False
    g.key("D", 10)
    assert player.center_x > home[0], "the player doesn't move on input"


def test_retry_after_death_brings_the_player_back(game: RealGame) -> None:
    _die(game)
    _retry(game)
    _assert_playable(game)
    assert game.named("Enemy A") is None and game.named("Enemy B") is not None  # (defeated stays defeated)
    assert _removed(game) == {"enemy_a"}  # (the player never recorded)


def test_a_save_after_retry_loads_with_the_player(game: RealGame) -> None:
    _die(game)
    _retry(game)
    game.save_load()
    _assert_playable(game)
    assert game.named("Enemy A") is None and _removed(game) == {"enemy_a"}


def test_saving_while_dead_never_records_the_player(game: RealGame) -> None:
    _die(game)
    assert game.window.save_manager.save_game("dead")  # (saving records what left the room)
    assert _removed(game) == {"enemy_a"}


def test_a_save_that_recorded_the_player_as_removed_loads_with_the_player(game: RealGame) -> None:
    """A save made after a retry before #750: no player in it, its id in the room's removed list."""
    from engine.scene_lifecycle_controller import handle_pending_scene_load

    manager = game.window.save_manager
    assert manager.save_game("old")
    path = Path(manager.save_dir) / "old.json"
    save = json.loads(path.read_text(encoding="utf-8"))
    save["entities"] = [e for e in save["entities"] if e.get("id") != PLAYER]
    written = 0
    for state in (save.get("state"), save.get("game_state")):
        for values in (state.get("variables"), state.get("values")) if isinstance(state, dict) else ():
            if isinstance(values, dict):
                values[room_memory.VAR] = {_arena(game): {"removed": ["enemy_a", PLAYER]}}
                written += 1
    assert written
    path.write_text(json.dumps(save, indent=2), encoding="utf-8")
    assert manager.load_game("old")
    handle_pending_scene_load(game.sc)
    game.frames(2)
    assert game.named("Enemy A") is None  # (the rest of the save's room memory still holds)
    _assert_playable(game)
    game.enter(game.room(HALL))  # (leaving rewrites the room's removed list: without the player)
    assert _removed(game) == {"enemy_a"}
    game.enter(game.room(ARENA))
    _assert_playable(game)


def test_a_player_id_in_this_games_room_memory_is_ignored_on_entry(game: RealGame) -> None:
    """Room memory that already holds the player's id (a game continued from such a save, before it left the room)."""
    game.enter(game.room(HALL))
    game.gs.set_var(room_memory.VAR, {_arena(game): {"removed": [PLAYER, "enemy_a"]}})
    game.enter(game.room(ARENA))
    assert game.named("Enemy A") is None
    _assert_playable(game)


def test_retry_brings_back_the_shared_player_of_a_studio_room(game: RealGame) -> None:
    room = game.room(COMMONS)
    game.enter(room)
    (shared,) = game.project.shared_players(room)
    file = Path(game.project.root) / game.path(room)
    thin = next(e for e in json.loads(file.read_text(encoding="utf-8"))["entities"] if e["id"] == shared)
    home = (float(thin["x"]), float(thin["y"]))
    wolf = game.named("Wolf").mesh_entity_data["id"]
    _die(game, "Wolf")
    _retry(game)
    _assert_playable(game, home, hp=12)
    assert game.named("Wolf") is None
    assert room_memory.removed_ids(game.window, room_memory.room_key(game.path(room))) == {wolf}  # (never the player)
    game.save_load()
    player = game.player()
    assert player is not None and player.mesh_entity_data["id"] == shared and game.named("Wolf") is None
