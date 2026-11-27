"""#751: a melee swing goes the way the attacker faces (the Lantern Road playtest, #745: the player could only hit east).

Played in a real hidden game (tests/_real_game.py). The player walks one way (WASD), stops, and
attacks standing still (Space): the dummy on that side is hurt, the one behind is not. An enemy (EnemyAI + Combat) that
met the player on its east side swings west once the player steps round to its west, and a chasing enemy is never
rotated (an upright character used to spin upside down while it chased). (HD-2D:
tests/test_hd2d_same_level.py's test_the_swing_goes_the_way_the_attacker_faces, on the floors demo's World.)
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

import engine.optional_arcade as optional_arcade
from tests._real_game import RealGame, author, batch, new_project, place, real_game

pytestmark = [
    pytest.mark.integration,  # (a generated project in a temporary folder; one hidden game window)
    pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)"),
]

ARENA, DEN = "Arena", "Den"
AT = (320.0, 240.0)  # the middle of a new room (20 x 15 tiles), clear of its walls
GAP = 44.0  # px between the player's centre and a dummy's: inside the swing ahead, outside it behind
WALK = {"left": ("A", (-1, 0)), "right": ("D", (1, 0)), "up": ("W", (0, 1)), "down": ("S", (0, -1))}
DUMMY = ("Health", {"max_hp": 50})


@pytest.fixture(scope="module")
def running(tmp_path_factory: pytest.TempPathFactory) -> Iterator[RealGame]:
    base = tmp_path_factory.mktemp("melee")
    project = new_project(base / "game")
    hero = [{"op": "add_behaviour", "entity_id": "Player", "behaviour": "Combat"},
            {"op": "set_behaviour_param", "entity_id": "Player", "behaviour": "Combat", "param": "cooldown", "value": 0.05},
            {"op": "add_behaviour", "entity_id": "Player", "behaviour": "Health"},
            *({"op": "set_behaviour_param", "entity_id": "Player", "behaviour": "Health", "param": k, "value": 500} for k in ("max_hp", "hp"))]
    author(project, project.add_room(ARENA), batch(place("Ahead", 100, 100, DUMMY, tag="enemy"),
                                                  place("Behind", 100, 400, DUMMY, tag="enemy")) + hero)
    author(project, project.add_room(DEN), place("Wolf", 100, 100, ("EnemyAI", {
        "target_tag": "player", "detect_radius": 200, "attack_radius": 60, "attack_cooldown": 0.3, "use_patrol": False}),
        ("Combat", {"target_tag": "player", "damage": 20, "cooldown": 0.3})))  # (the player is shared; beyond its defence)
    launch = base / "elsewhere"
    launch.mkdir()
    with real_game(project, launch) as started:
        yield started


@pytest.fixture()
def game(running: RealGame) -> RealGame:
    return running.resume()


def _hp(g: RealGame, name: str) -> float:
    if name == "Player":
        return float(next(b for b in g.player().mesh_behaviours_runtime if type(b).__name__ == "Health").hp)
    return float(g.behaviour(name, "Health").hp)


@pytest.mark.parametrize("way", list(WALK))
def test_the_player_hits_the_way_it_last_walked_while_standing_still(game: RealGame, way: str) -> None:
    game.enter(game.room(ARENA))
    hero = game.player()
    hero.center_x, hero.center_y = AT
    key, (fx, fy) = WALK[way]
    game.key(key, 4)  # walk that way, then let go: standing, facing it
    game.frames(2)
    assert (hero.mesh_velocity_x, hero.mesh_velocity_y) == (0.0, 0.0), "standing still when it swings"
    x, y = hero.center_x, hero.center_y
    for name, side in (("Ahead", 1), ("Behind", -1)):
        dummy = game.named(name)
        dummy.center_x, dummy.center_y = x + side * fx * GAP, y + side * fy * GAP
    game.frames(1)
    game.key("SPACE", 1)
    game.frames(15)  # (the swing's hitbox lives 0.2 s)
    assert _hp(game, "Ahead") < 50.0, f"facing {way}: the dummy {way} of the player is hit"
    assert _hp(game, "Behind") == 50.0, f"facing {way}: the dummy behind is not"


def test_an_enemy_swings_at_the_player_wherever_it_stands(game: RealGame) -> None:
    """The wolf meets the player east of it and hits it; the player steps round to its west, still in reach: the wolf's
    next swing goes west (it used to keep swinging the way it last chased)."""
    game.enter(game.room(DEN))
    wolf, hero = game.named("Wolf"), game.player()
    wolf.center_x, wolf.center_y = AT
    hero.center_x, hero.center_y = AT[0] + GAP, AT[1]
    start = _hp(game, "Player")
    game.frames(20)
    east = _hp(game, "Player")
    assert east < start, "hit while east of the wolf"
    hero.center_x, hero.center_y = wolf.center_x - GAP, wolf.center_y
    game.frames(30)  # (past its cooldown: it swings again, standing its ground)
    assert _hp(game, "Player") < east, "hit while west of the wolf"



def test_a_chasing_enemy_stays_upright_and_still_hits(game: RealGame) -> None:
    """The wolf chases a player below and to its left: its picture is never turned (it used to be rotated toward the
    player every frame, an upright character spinning upside down), and its swing still lands."""
    game.enter(game.room(DEN))
    wolf, hero = game.named("Wolf"), game.player()
    wolf.center_x, wolf.center_y = AT
    hero.center_x, hero.center_y = AT[0] - 120.0, AT[1] - 80.0
    start, turned = _hp(game, "Player"), set()
    for _ in range(120):
        game.frames(1)
        turned.add(wolf.angle)
    assert wolf.center_x < AT[0] and wolf.center_y < AT[1], "it chased the player"
    assert turned == {0.0}, "never rotated"
    assert _hp(game, "Player") < start, "its attack still hits"
