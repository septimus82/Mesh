"""HD-2D online M3-4: using, attacking and picking up respect floors, in single-player and the net authority alike
(owner decision D8 (a)).

engine.hd2d.world.same_level is the one rule (vertical reach, BODY, and no floor between the two). Each case puts an
actor and a target in the floors demo's crossing (ground, west stairs, a platform and landing 2 m up, a 2 m bridge
deck over an underpass) and asks both runtimes:

- single-player, through the game's own code on the World the game builds (tests.test_hd2d_net_parity's
  single_player_world): engine.interaction.perform_interaction on a lever, Combat's hitbox then the Hitbox behaviour on
  an enemy with Health, a Collectible touched and a PickupCollectible used;
- the authority, through SceneRoom.step with a v1 input frame: ``use`` (its lever opens its gate), ``attack`` (its
  enemy loses HP), ``take`` (its dropped loot is held).

Every answer, in both runtimes, must be the case's. Characters stand where World.stand puts them (asserted); objects
stand at the floor under their centre, as Studio places them, or float where a case says. Behaviours are made from the
classes the game makes them from (the behaviour registry), so a test that patches what they look up patches what
runs, whatever re-imported the behaviour modules earlier in the session."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator, cast
from unittest.mock import MagicMock

import pytest

import engine.optional_arcade as optional_arcade
from engine.combat_model import TargetState
from engine.hd2d.settings import PIXELS_PER_METRE as M
from engine.hd2d.settings import parse_hd2d
from engine.hd2d.world import BODY, World, build_world, same_level
from engine.physics_model import entity_aabb, entity_shape, shapes_overlap
from mesh_net import protocol as wire
from mesh_net.scene_room import COOP_SCENE, Body, Player, SceneRoom, coop_files, disposable_project
from tests.test_hd2d_net_parity import SCENE, single_player_world, sprite

pytestmark = pytest.mark.integration  # (builds a project in a folder, loads its room from files)

REPO = Path(__file__).resolve().parents[1]
LEVER, GATE, ENEMY = "lever", "gate", "bandit"
BOX = {"collider": {"kind": "box", "w": 64, "h": 64}}  # every target's: it meets the actor's feet and its hitbox
TARGETS = [
    {"id": LEVER, "name": "Lever", "sprite": "assets/sprites/starter_sign.png", "x": 64.0, "y": 64.0, "components": BOX,
     "behaviours": ["SwitchInteract"], "behaviour_config": {"SwitchInteract": {"event_id": "open", "one_shot": True}}},
    {"id": GATE, "name": "Gate", "x": 160.0, "y": 64.0, "behaviours": ["DoorLock"],
     "behaviour_config": {"DoorLock": {"starts_locked": True, "unlock_event": "open"}}},
    {"id": ENEMY, "name": "Bandit", "tag": "enemy", "x": 256.0, "y": 64.0, "components": BOX, "behaviours": ["Health"],
     "behaviour_config": {"Health": {"max_hp": 3.0}}},
]

DECK_AT = (16.0 * M, 12.0 * M + 18.0)  # sprite centre: feet at (16 m, 12 m), on the deck or under it
OPEN_AT = (16.0 * M, 3.0 * M + 18.0)  # on the open ground south of the crossing
STAIRS_AT = (10.0 * M, 5.5 * M + 18.0)  # half way up the west stairs (feet 0.5 m up: they rise 0.5 m a metre north)
TOP_AT = (10.0 * M, 8.0 * M + 18.0)  # near the stairs' top (1.75 m), the landing (2 m) a metre north
# name: (actor's sprite centre, its floor (m), the target's offset from its feet (px), the target's elevation: the
# floor under its centre nearest this many metres, or a float in px), the answer
CASES: dict[str, tuple[tuple[float, float], float, tuple[float, float], tuple[str, float] | float, bool]] = {
    "deck, ground directly beneath": (DECK_AT, 2.0, (0.0, 0.0), ("floor", 0.0), False),
    "deck, hung under it a metre up": (DECK_AT, 2.0, (0.0, 0.0), 1.0 * M, False),  # (in reach: the deck is between)
    "under the deck, ground": (DECK_AT, 0.0, (0.0, 0.0), ("floor", 0.0), True),
    "deck, deck": (DECK_AT, 2.0, (16.0, 32.0), ("floor", 2.0), True),
    "ground, ground": (OPEN_AT, 0.0, (16.0, 32.0), ("floor", 0.0), True),
    "stairs, a metre up the stairs": (STAIRS_AT, 0.5, (16.0, 32.0), ("floor", 1.0), True),
    "stairs' top, landing": (TOP_AT, 1.75, (16.0, 32.0), ("floor", 2.0), True),
    "stairs, just within reach above": (STAIRS_AT, 0.5, (16.0, 32.0), 0.5 * M + BODY * M - 0.5, True),
    "stairs, just beyond reach above": (STAIRS_AT, 0.5, (16.0, 32.0), 0.5 * M + BODY * M + 0.5, False),
    # (saved on the ground at the stairs' foot, where they are already 0.1 m up: within a step, so no floor between)
    "stairs, an object at their foot": (STAIRS_AT, 0.5, (16.0, -25.6), 0.0, True),
}


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """The floors demo's project with a lever (and its gate) and an enemy, as the current folder while this runs."""
    sys.path.insert(0, str(REPO / "tooling"))
    try:
        import hd2d_floors_demo
    finally:
        sys.path.remove(str(REPO / "tooling"))
    built = hd2d_floors_demo.build(tmp_path_factory.mktemp("level") / "proj")
    files = {p.relative_to(built).as_posix(): p.read_bytes() for p in built.rglob("*") if p.is_file()}
    assert TARGETS[0]["sprite"] in files
    scene = json.loads(files[SCENE])
    scene["entities"] += json.loads(json.dumps(TARGETS))
    with disposable_project({**files, SCENE: json.dumps(scene).encode()}, scaffold=False) as root:
        yield root


@pytest.fixture(scope="module")
def room(project: Path) -> SceneRoom:
    room = SceneRoom(project / SCENE, project)
    assert room.world is not None and set(room.levers) == {LEVER} and set(room.enemies) == {ENEMY}
    return room


@pytest.fixture(scope="module")
def world(project: Path, room: SceneRoom) -> World:
    world = single_player_world(project)[0]
    assert world.collision_digest() == room.digest, "single-player's World is the authority's"
    return world


def placed(room: SceneRoom, case: str) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """The case's actor (sprite centre px, elevation px: where World.stand stands it) and target (centre, elevation)."""
    (ax, ay), floor, (dx, dy), spec, _ = CASES[case]
    assert room.world is not None
    stood = room._stand(Body(ax, ay, *room._template_size(), room.template), floor)
    assert stood is not None and abs(stood[0] - floor) < 0.05, f"{case}: the actor stands on its floor"
    feet = entity_aabb(Body(ax, ay, *room._template_size(), room.template))
    tx, ty = feet.x + dx, feet.y + dy
    if isinstance(spec, tuple):
        tz = min((h for h, _s in room.world.heights_at(tx / M, ty / M)), key=lambda h: abs(h - spec[1]))
        assert abs(tz - spec[1]) <= 0.25, f"{case}: the target's floor"
        tz *= M
    else:
        tz = spec
    return (ax, ay, round(stood[0] * M, 3)), (tx, ty, round(tz, 3))


def authority(room: SceneRoom, actor: tuple[float, float, float], target: tuple[float, float, float],
              action: str) -> bool:
    """One tick of the authority: a player (facing right) at ``actor`` sends ``action`` at the lever or enemy (its
    loot dropped, for ``take``) moved to ``target``. Whether it took effect."""
    tx, ty, tz = target
    lever = room.levers[LEVER][0]
    lever.update(x=tx, y=ty, elevation=tz)
    room.used.clear()
    room.locked = {GATE}
    enemy = room.enemies[ENEMY]
    enemy.body.center_x, enemy.body.center_y = tx, ty
    enemy.body.mesh_entity_data["elevation"] = tz
    enemy.state, enemy.dropped, enemy.holder = TargetState(hp=3.0, max_hp=3.0), action == "take", None
    eid = room.join(Player(Body(actor[0], actor[1], *room._template_size(), {**room.template, "elevation": actor[2]}),
                           facing=0))
    room.input(eid, {"v": wire.VERSION, "type": "input", "entity": eid, "seq": 1, "dx": 0, "dy": 0, "action": action})
    room.step()
    player = room.leave(eid)
    return {"use": GATE not in room.locked, "attack": enemy.state.hp < 3.0, "take": enemy.holder is player}[action]


def behaviour(name: str) -> Any:
    """The class the game makes ``name`` from (engine.behaviours.registry.create_behaviour's)."""
    from engine.behaviours import load_builtin_behaviours
    from engine.behaviours.registry import BEHAVIOUR_REGISTRY

    load_builtin_behaviours()
    return BEHAVIOUR_REGISTRY[name]


class Thing(SimpleNamespace):
    """A game sprite as the behaviours read it: hashable, as Arcade's are (the Hitbox keeps what it hit in a set)."""

    def __hash__(self) -> int:  # type: ignore[override]
        return id(self)


class Lever:
    """A usable object's behaviour (what interaction asks of SwitchInteract): records being used."""

    def __init__(self) -> None:
        self.used = False

    def on_interact(self, window: Any, actor: Any) -> None:
        self.used = True


def single_player(world: World | None, room: SceneRoom, actor_at: tuple[float, float, float],
                  target: tuple[float, float, float], monkeypatch: pytest.MonkeyPatch) -> dict[str, bool]:
    """The game's own code, ``window.hd2d_world`` the World (None: a 2D room), an actor facing right at ``actor_at``
    and each kind of target at ``target``: what took effect. Sprites touch where their collider boxes overlap (the
    authority's test; Arcade's own needs pictures)."""
    from engine.interaction import perform_interaction

    Collectible, Combat, Health = behaviour("Collectible"), behaviour("Combat"), behaviour("Health")
    Hitbox, PickupCollectible = behaviour("Hitbox"), behaviour("PickupCollectible")
    monkeypatch.setattr(optional_arcade.arcade, "check_for_collision",
                        lambda a, b: shapes_overlap(entity_shape(a), entity_shape(b)))
    x, y, z = actor_at
    actor: Any = sprite(x, y, room._template_size(), {**room.template, "elevation": z, "facing": "right"})
    actor.mesh_tag = actor.mesh_name = "player"
    actor.angle, actor.change_x, actor.change_y = 0.0, 0.0, 0.0

    def target_sprite(**extra: Any) -> Any:
        made = Thing(**vars(sprite(target[0], target[1], (0.0, 0.0), {"id": "target", "x": target[0], "y": target[1],
                                                                      "elevation": target[2], "components": BOX,
                                                                      **extra})))
        made.mesh_tag, made.mesh_name, made.visible = extra.get("tag", ""), "target", True
        made.remove_from_sprite_lists = lambda: None
        return made

    def window(**attrs: Any) -> MagicMock:
        made = MagicMock()
        made.hd2d_world, made.game_state_controller = world, None
        for key, value in attrs.items():
            setattr(made, key, value)
        return made

    done = {}
    lever = target_sprite()
    lever.mesh_behaviours_runtime = [Lever()]
    perform_interaction(window(all_sprites=[actor, lever]), actor=actor)
    done["use"] = lever.mesh_behaviours_runtime[0].used

    enemy = target_sprite(tag="enemy")
    hits = window()
    health = Health(enemy, hits, max_hp=3.0, hp=3.0)
    enemy.mesh_behaviours_runtime = [health]
    spawned: list[Any] = []

    def create(data: dict[str, Any]) -> Any:
        spawned.append(SimpleNamespace(center_x=data["x"], center_y=data["y"], width=room.hitbox, height=room.hitbox,
                                       mesh_entity_data=data, remove_from_sprite_lists=lambda: None))
        return spawned[-1]

    hits.scene_controller = SimpleNamespace(_create_sprite=create, add_sprite_to_layer=lambda *_a: None,
                                            all_sprites=[actor, enemy])
    assert Combat(actor, hits, damage=1.0, range=room.reach, hitbox_size=room.hitbox, cooldown=1.0).attack()
    (hitbox,) = spawned
    hitbox.mesh_tag = ""
    hits.scene_controller.all_sprites.append(hitbox)
    Hitbox(hitbox, hits, **hitbox.mesh_entity_data["behaviour_config"]["Hitbox"]).update(0.01)
    done["attack"] = health.hp < 3.0

    item, picked = target_sprite(), []
    touch = window(find_sprite_by_name=lambda _name: actor, should_collide=lambda _a, _b: True,
                   on_collectible_picked=lambda _item, who: picked.append(who))
    Collectible(item, touch, collect_by_name="player", auto_remove=False).update(0.0)
    done["collect"] = picked == [actor]

    item = target_sprite()
    pickup = window()
    item.mesh_behaviours_runtime = [PickupCollectible(item, pickup, remove_on_collect=False)]
    pickup.all_sprites = [actor, item]
    perform_interaction(pickup, actor=actor)
    done["pickup"] = item.mesh_behaviours_runtime[0]._already_collected
    return done


@pytest.mark.parametrize("case", list(CASES))
def test_both_runtimes_give_the_floor_rules_answer(case: str, room: SceneRoom, world: World,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    """Use, attack and pick up: refused across floors (a deck over the ground: out of reach; something hung under the
    deck within reach: the deck between), accepted on one floor, between stair neighbours and from the stairs' top to
    the landing, and at the reach's edge exactly as BODY says, in both runtimes."""
    actor, target = placed(room, case)
    expected = CASES[case][-1]
    done = {f"single-player {k}": v for k, v in single_player(world, room, actor, target, monkeypatch).items()}
    done.update({f"authority {a}": authority(room, actor, target, a) for a in ("use", "attack", "take")})
    assert done == dict.fromkeys(done, expected), f"{case}: {done}"
    assert same_level(world, sprite(*actor[:2], room._template_size(), {**room.template, "elevation": actor[2]}),
                      SimpleNamespace(center_x=target[0], center_y=target[1], width=0.0, height=0.0,
                                      mesh_entity_data={"elevation": target[2], "components": BOX})) is expected


def test_without_an_hd2d_world_nothing_changes(room: SceneRoom, monkeypatch: pytest.MonkeyPatch) -> None:
    """A 2D room: everything is on one level whatever its elevation says, in both runtimes (the deck case, refused in
    the HD-2D room, takes effect everywhere)."""
    actor, target = placed(room, "deck, ground directly beneath")
    a = sprite(*actor[:2], room._template_size(), {**room.template, "elevation": actor[2]})
    b = SimpleNamespace(center_x=target[0], center_y=target[1], width=0.0, height=0.0,
                        mesh_entity_data={"elevation": target[2]})
    assert same_level(None, a, b) and same_level(MagicMock(), a, b) and same_level(cast(Any, SimpleNamespace()), a, b)
    assert all(single_player(None, room, actor, target, monkeypatch).values())
    with disposable_project(coop_files()) as root:
        flat = SceneRoom(root / COOP_SCENE, root)
    assert flat.world is None
    (lever_id, (lever, _cfg)), = flat.levers.items()
    gate = next(i for i, (_b, c) in flat.doors.items() if c.get("unlock_event") == _cfg["event_id"])
    eid = flat.join(Player(Body(float(lever["x"]), float(lever["y"]), *flat._template_size(),
                                {**flat.template, "elevation": 64.0})))
    flat.input(eid, {"v": wire.VERSION, "type": "input", "entity": eid, "seq": 1, "dx": 0, "dy": 0, "action": "use"})
    flat.step()
    assert gate not in flat.locked and lever_id in flat.used, "a 2D room's lever is used whatever the elevations"


@pytest.mark.parametrize("answer", [True, False])
def test_every_consumer_asks_the_one_rule_and_nothing_else(answer: bool, room: SceneRoom, world: World,
                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    """Swap engine.hd2d.world.same_level for a constant where the code that runs looks it up (the globals of the
    behaviour classes the game makes, of engine.interaction, and engine.hd2d.world for the authority's lazy import):
    every action in both runtimes follows it (a refused case taking effect, an accepted one refused), so neither has
    a level check of its own."""
    from engine.interaction import perform_interaction

    def constant(_world: Any, _a: Any, _b: Any) -> bool:
        return answer

    for name in ("Hitbox", "Collectible", "Projectile", "DamageOnTouch"):
        monkeypatch.setitem(behaviour(name).update.__globals__, "same_level", constant)
    monkeypatch.setitem(perform_interaction.__globals__, "same_level", constant)
    monkeypatch.setattr(sys.modules["engine.hd2d.world"], "same_level", constant)
    actor, target = placed(room, "under the deck, ground" if not answer else "deck, ground directly beneath")
    done = {f"single-player {k}": v for k, v in single_player(world, room, actor, target, monkeypatch).items()}
    done.update({f"single-player {k}": v for k, v in hurt(world, room, actor, target, monkeypatch).items()})
    done.update({f"authority {a}": authority(room, actor, target, a) for a in ("use", "attack", "take")})
    assert done == dict.fromkeys(done, answer), done


def hurt(world: World | None, room: SceneRoom, actor_at: tuple[float, float, float], target: tuple[float, float, float],
         monkeypatch: pytest.MonkeyPatch) -> dict[str, bool]:
    """Single-player's other ways to hurt (the authority has neither), the actor at ``actor_at`` and the target at
    ``target``: a Shooter's shot at an enemy, and a DamageOnTouch hazard at the actor. What took effect."""
    DamageOnTouch, Health = behaviour("DamageOnTouch"), behaviour("Health")
    Projectile, Shooter = behaviour("Projectile"), behaviour("Shooter")
    monkeypatch.setattr(optional_arcade.arcade, "check_for_collision",
                        lambda a, b: shapes_overlap(entity_shape(a), entity_shape(b)))

    def thing(at: tuple[float, float, float], data: dict[str, Any], tag: str) -> Any:
        made = Thing(**vars(sprite(at[0], at[1], (0.0, 0.0), {**data, "elevation": at[2]})))
        made.mesh_tag = made.mesh_name = tag
        made.remove_from_sprite_lists = lambda: None
        return made

    window = MagicMock()
    window.hd2d_world, window.game_state_controller = world, None
    actor = thing(actor_at, room.template, "player")
    enemy = thing(target, {"components": BOX}, "enemy")
    enemy.mesh_behaviours_runtime = [Health(enemy, window, max_hp=3.0, hp=3.0)]
    spawned: list[Any] = []

    def create(data: dict[str, Any]) -> Any:
        spawned.append(thing((data["x"], data["y"], 0.0), {}, "shot"))
        spawned[-1].width = spawned[-1].height = 8.0
        spawned[-1].config = data["behaviour_config"]["Projectile"]
        return spawned[-1]

    window.scene_controller = SimpleNamespace(_create_sprite=create, add_sprite_to_layer=lambda *_a: None,
                                              all_sprites=[actor, enemy])
    Shooter(actor, window, target_tag="enemy", damage=1.0)._spawn_projectile(0.0)
    (shot,) = spawned
    assert shot.mesh_attacker is actor, "the shot says who fired it"
    Projectile(shot, window, **shot.config).update(0.01)
    done = {"shot": enemy.mesh_behaviours_runtime[0].hp < 3.0}

    actor.mesh_behaviours_runtime = [Health(actor, window, max_hp=3.0, hp=3.0)]
    window.find_sprite_by_name = lambda _name: actor
    window.should_collide = lambda _a, _b: True
    hazard = thing(target, {"components": BOX}, "spikes")
    DamageOnTouch(hazard, window, target_name="player", damage=1.0).update(0.01)
    done["touch"] = actor.mesh_behaviours_runtime[0].hp < 3.0
    return done


@pytest.mark.parametrize("case", ["deck, ground directly beneath", "under the deck, ground"])
def test_shots_and_hurtful_touches_respect_floors_too(case: str, room: SceneRoom, world: World,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    """A Shooter's shot hits for its shooter, and a DamageOnTouch hazard touches, only on one level."""
    actor, target = placed(room, case)
    assert hurt(world, room, actor, target, monkeypatch) == dict.fromkeys(("shot", "touch"), CASES[case][-1])


def test_the_debugger_says_when_its_on_another_floor(room: SceneRoom, world: World) -> None:
    """debug_interaction's reach rules (engine.runtime_diagnose) in an HD-2D room: from the deck, a lever directly
    beneath is in reach and faced, and the ``level`` rule says it is on another floor, so nothing is chosen; from under
    the deck it is on the player's level and chosen, as the game chooses. A 2D room's rules are as before."""
    from engine import interaction, runtime_diagnose

    for case, ok in (("deck, ground directly beneath", False), ("under the deck, ground", True)):
        (x, y, z), (tx, ty, tz) = placed(room, case)
        actor = sprite(x, y, room._template_size(), {**room.template, "elevation": z, "facing": "right"})
        lever: Any = Thing(**vars(sprite(tx, ty, (0.0, 0.0), {"id": "lever", "elevation": tz, "components": BOX})))
        lever.mesh_behaviours_runtime, lever.visible = [Lever()], True
        window = SimpleNamespace(hd2d_world=world, all_sprites=[actor, lever], get_flag=None)
        found = {c["code"]: c for c in runtime_diagnose._reach_and_selection(window, lever, actor)}
        assert found["distance"]["ok"] and found["facing"]["ok"], case
        assert found["level"]["ok"] is ok, case
        if ok:
            assert found["selection"]["ok"] and found["selection"]["detail"]["chosen"] == "lever", case
            assert interaction.resolve_interaction_candidate(window, actor=actor) is not None, "the game agrees"
        else:
            assert "another floor" in found["level"]["message"] and "selection" not in found, case
            assert interaction.resolve_interaction_candidate(window, actor=actor) is None, "the game agrees"
    flat = SimpleNamespace(hd2d_world=None, all_sprites=[actor, lever], get_flag=None)
    assert "level" not in {c["code"] for c in runtime_diagnose._reach_and_selection(flat, lever, actor)}


def hill() -> World:
    """A room of sculpted ground with one hill (2.5 m high, 6 m across): its flank rises about 0.6 m a metre at x 16 m,
    y 8.5 m to 9.5 m."""
    from engine import project_ops as ops

    room = {"entities": [], "settings": {"world_width": 1024, "world_height": 768,
                                         "hd2d": {"ground": {"to": [1024, 768]}}}}
    hd2d = ops.sculpt_terrain_stroke(room, "raise", [[512, 384, 80]], 192)["settings"]["hd2d"]
    world = build_world(parse_hd2d(hd2d), [], lambda rel: REPO / rel)[0]
    assert world is not None and world.terrain is not None
    return world


def ground_at(world: World, x: float, y: float) -> float:
    """The sculpted ground's height (m) at (x, y) m."""
    ((h, surface),) = world.heights_at(x, y)
    assert surface.floor == "ground"
    return h


def test_the_ground_never_counts_as_a_floor_between() -> None:
    """A heightfield can't lie between two things above it: on a hill's flank (about 0.6 m a metre), an object
    standing at its centre whose collider is 0.75 m uphill of it, and one a later raise of the ground left buried more
    than a step deep, are both on the level of a character a metre further up the slope."""
    world = hill()

    def hero(feet_y: float) -> SimpleNamespace:  # (a character standing with its feet at (16 m, feet_y m))
        made = SimpleNamespace(center_x=16.0 * M, center_y=feet_y * M + 18.0, width=32.0, height=48.0,
                               mesh_entity_data={"components": {"collider": {"kind": "box", "auto": True}}})
        box = entity_aabb(made)
        stood = world.stand(box.x / M, box.y / M, ground_at(world, box.x / M, box.y / M), box.w / 2 / M, box.h / 2 / M)
        assert stood is not None
        made.mesh_entity_data["elevation"] = round(stood[0] * M, 3)
        return made

    offset = SimpleNamespace(center_x=16.0 * M, center_y=8.5 * M, width=32.0, height=32.0, mesh_entity_data={
        "elevation": round(ground_at(world, 16.0, 8.5) * M, 3),
        "components": {"collider": {"kind": "box", "w": 16, "h": 16, "offset_y": 24}}})  # (0.75 m uphill)
    assert ground_at(world, 16.0, 8.5 + 0.75) - ground_at(world, 16.0, 8.5) > 0.35, "its collider's ground: past a step"
    buried = SimpleNamespace(center_x=16.0 * M, center_y=8.0 * M, width=32.0, height=32.0,
                             mesh_entity_data={"elevation": 0.0})  # (saved before the hill was raised)
    assert ground_at(world, 16.0, 8.0) > 0.35, "buried more than a step deep"
    for thing, up in ((offset, hero(9.5)), (buried, hero(9.0))):
        assert same_level(world, up, thing) and same_level(world, thing, up)
