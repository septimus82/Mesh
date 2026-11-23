"""HD-2D online M3-3: walk-in doors respect floors, in single-player and the net authority alike (owner decision D8 (a)
and (c)).

A door fires only for a player on its level: engine.hd2d.world.same_level (M3-4's rule) between the player and the
door's doorway at engine.hd2d.world.door_level (the floor one stands on there nearest the door's saved elevation). Each
case puts one walk-in door (a 16 x 16 px area) in the floors demo's crossing (tests/test_mesh_net_hd2d.py's world
files: ground, west stairs rising 0.5 m a metre, a solid platform and landing 2 m up, a 2 m bridge deck over an open
underpass) and walks one actor with one scripted input sequence in both runtimes:

- single-player: the game's PlayerController through World.move at dt 1/20 (tests/test_hd2d_net_parity.py's
  run_single_player), and at each tick's position the game's SceneTransition (the class the behaviour registry makes)
  asked whether the door fires, its window's ``hd2d_world`` the World the game builds;
- the authority: mesh_net.world.World stepping its rooms with v2 input frames, the player transferred through the door.

The first tick the door fires in single-player must be the tick the authority transfers, or neither may happen."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from engine.hd2d.settings import PIXELS_PER_METRE as M
from engine.hd2d.world import World, door_level, same_level
from mesh_net import protocol as wire
from mesh_net.scene_room import Body, Unsupported, disposable_project
from mesh_net.world import Door
from mesh_net.world import World as NetWorld
from tests.test_hd2d_net_parity import run_single_player, single_player_world, ticks
from tests.test_hd2d_same_level import behaviour, ground_at, hill
from tests.test_mesh_net_hd2d import crossing, door, world_files  # noqa: F401  (crossing: a fixture)

pytestmark = pytest.mark.integration  # (builds a project in a folder, loads its rooms from files)

FEET = 18.0  # px: the template's sprite centre is this far above its feet
AREA = 16.0  # px: each door's area, square
# name: (door (x m, y m, saved elevation px), actor (feet x m, feet y m, its floor m), route, whether it fires)
CASES: dict[str, tuple[tuple[float, float, float], tuple[float, float, float], list[tuple[int, int, int]], bool]] = {
    # a ground door under the deck (saved at 0): only for the one under the deck
    "ground door, deck actor": ((15.0, 12.0, 0.0), (16.0, 12.0, 2.0), [(-1, 0, 11)], False),
    "ground door, ground actor": ((15.0, 12.0, 0.0), (16.0, 12.0, 0.0), [(-1, 0, 11)], True),
    # a door on the deck (Studio placed it on the deck: saved 2 m up): only for the one on the deck
    "deck door, deck actor": ((15.0, 12.0, 2.0 * M), (16.0, 12.0, 2.0), [(-1, 0, 11)], True),
    "deck door, ground actor": ((15.0, 12.0, 2.0 * M), (16.0, 12.0, 0.0), [(-1, 0, 11)], False),
    # Studio's Add door saves no elevation: one added on the solid platform 2 m up is on the platform, the only floor to
    # stand on there (door_level), so it fires for the one walking on the platform
    "platform door saved at 0, platform actor": ((10.0, 12.0, 0.0), (11.5, 12.0, 2.0), [(-1, 0, 11)], True),
    # on the stairs (1 m up there; saved at 0) and at their foot: within reach of one walking the stairs
    "stairs door, actor walking up": ((10.0, 6.5, 0.0), (10.0, 3.5, 0.0), [(0, 1, 30)], True),
    "door at the stairs' foot, actor walking down": ((10.0, 4.5, 0.0), (10.0, 7.0, 1.25), [(0, -1, 30)], True),
}


def walk(files: dict[str, bytes], case: str) -> tuple[list[bool], list[bool], int | None, dict[str, Any]]:
    """The case walked in both runtimes: per tick whether single-player's door fired, and whether the door's area
    overlaps the player's picture at all (the planar test alone); the tick the authority transferred (None: never);
    and the door's doorway as door_level gives it."""
    (dx_m, dy_m, saved), (fx, fy, floor), route, _ = CASES[case]
    entity = door("door", dx_m * M, dy_m * M, "high", AREA)
    if saved:
        entity["elevation"] = saved
    script = ticks(route)
    with disposable_project(world_files(files, [entity]), scaffold=False) as root:
        net = NetWorld(root)
        room = net.defs["start"].proto
        size = room._template_size()
        at = Body(fx * M, fy * M + FEET, *size, dict(room.template))
        stood = room._stand(at, floor)
        assert stood is not None and abs(stood[0] - floor) < 0.05, f"{case}: the actor stands on its floor"
        z = round(stood[0] * M, 3)
        sp = single_player_world(root)
        single = run_single_player(sp, room, [(at.center_x, at.center_y, z)], [script])[0]
        fired, planar = [], []
        SceneTransition = behaviour("SceneTransition")
        for x, y, elevation, _floor, _blocked in single:
            actor = Picture(center_x=x, center_y=y, width=size[0], height=size[1], mesh_tag="player",
                            mesh_name="hero", mesh_entity_data={**room.template, "elevation": elevation})
            requests: list[str] = []
            window = SimpleNamespace(scene_controller=SimpleNamespace(all_sprites=[actor]), hd2d_world=sp[0],
                                     request_scene_change=requests.append, set_next_spawn_point=lambda _s: None,
                                     console_log=lambda _m: None)
            sprite = Picture(center_x=entity["x"], center_y=entity["y"], width=32.0, height=32.0, mesh_tag="door",
                             mesh_name="door", mesh_entity_data=entity)
            SceneTransition(sprite, window, **entity["behaviour_config"]["SceneTransition"]).update(1 / 20)
            fired.append(requests == ["deck"])
            planar.append(Door("d", "deck", "", entity["x"], entity["y"], AREA / 2, AREA / 2).touches(
                Body(x, y, *size, {})))
        level = door_level(sp[0], SimpleNamespace(center_x=entity["x"], center_y=entity["y"], width=AREA,
                                                  height=AREA, mesh_entity_data=entity)).mesh_entity_data
        return fired, planar, authority(net, at, z, script), level


def authority(net: NetWorld, at: Body, z: float, script: list[tuple[int, int]]) -> int | None:
    """A player joined at ``at`` (stood at ``z`` px) given ``script``, one v2 input frame a tick: the tick (1-based)
    it was transferred through a door, or None."""
    pid, _ = net.connect(None)
    m = net.members[pid]
    hub = net.instances[m.instance or ""]
    assert m.eid is not None
    body = hub.room.players[m.eid].body
    body.center_x, body.center_y = at.center_x, at.center_y
    body.mesh_entity_data["elevation"] = z
    stood = hub.room._stand(body, z / M)
    assert stood is not None
    body.mesh_hd2d_floor = stood[1]
    hub.touching[m.eid] = net._doors_touched(hub, body)
    assert not hub.touching[m.eid], "nothing touched where it starts"
    for tick, (dx, dy) in enumerate(script, 1):
        net.input(pid, {"v": wire.VERSION, "type": "input", "room": m.instance, "entity": m.eid, "seq": tick,
                        "dx": dx, "dy": dy})
        net.step()
        if m.instance != hub.id:
            assert net.instances[m.instance or ""].key == "deck"
            return tick
    return None


class Picture(SimpleNamespace):
    """A sprite with the bounds SceneTransition.update reads."""

    @property
    def left(self) -> float:
        return float(self.center_x - self.width / 2)

    @property
    def right(self) -> float:
        return float(self.center_x + self.width / 2)

    @property
    def bottom(self) -> float:
        return float(self.center_y - self.height / 2)

    @property
    def top(self) -> float:
        return float(self.center_y + self.height / 2)


@pytest.mark.parametrize("case", list(CASES))
def test_a_door_fires_only_on_its_level_on_the_same_tick_in_both_runtimes(case: str, crossing: dict[str, bytes]) -> None:  # noqa: F811
    """Refused across floors (a ground door under the deck for one on the deck; a door on the deck for one under it),
    accepted on one floor, on and at the foot of the stairs, and on the platform a door was added to at 0; in both
    runtimes, on the same tick. Where refused, the actor did cross the door's area: only the level kept it shut."""
    fired, planar, transferred, _ = walk(crossing, case)
    first = next((t for t, f in enumerate(fired, 1) if f), None)
    assert first == transferred, f"{case}: single-player fired first on tick {first}, the authority moved on {transferred}"
    assert (first is not None) is CASES[case][-1], f"{case}: {first}"
    assert any(planar), f"{case}: the actor crosses the door's area"


def test_a_door_is_on_the_floor_one_stands_on_nearest_its_saved_elevation(crossing: dict[str, bytes]) -> None:  # noqa: F811
    """door_level: under the open deck (the ground and the deck both stand) a door saved at 0 is on the ground and one
    saved 2 m up on the deck; on the solid platform, where only its top stands, one saved at 0 is on the platform; on
    the stairs, where they are 1 m up, at 1 m."""
    assert walk(crossing, "ground door, ground actor")[3] == {"elevation": 0.0}
    assert walk(crossing, "deck door, deck actor")[3] == {"elevation": 2.0 * M}
    assert walk(crossing, "platform door saved at 0, platform actor")[3] == {"elevation": 2.0 * M}
    assert walk(crossing, "stairs door, actor walking up")[3] == {"elevation": 1.0 * M}


@pytest.mark.parametrize("answer", [True, False])
def test_both_runtimes_ask_the_one_rule_and_nothing_else(answer: bool, crossing: dict[str, bytes],  # noqa: F811
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    """Swap engine.hd2d.world.same_level for a constant where the code that runs looks it up (the globals of the
    SceneTransition class the game makes, and engine.hd2d.world for the authority's lazy import): the door follows it
    in both runtimes (a refused case fires, an accepted one doesn't), so neither has a level check of its own."""
    def constant(_world: Any, _a: Any, _b: Any) -> bool:
        return answer

    monkeypatch.setitem(behaviour("SceneTransition").update.__globals__, "same_level", constant)
    monkeypatch.setattr(sys.modules["engine.hd2d.world"], "same_level", constant)
    fired, _planar, transferred, _ = walk(crossing, "ground door, deck actor" if answer else "ground door, ground actor")
    assert any(fired) is answer and (transferred is not None) is answer, (fired, transferred)


def test_a_multi_height_door_room_now_loads_and_decides_per_player(crossing: dict[str, bytes]) -> None:  # noqa: F811
    """M1-A-2 refused a door whose area has more than one floor height (it fired for a player on any of them); the rule
    now decides per player, so the room loads, and its door carries the room's World and its level. A door anchored on
    its picture's base (``area_at: base``) is still refused: single-player measures that base from Arcade's hit box."""
    with disposable_project(world_files(crossing, [door("bridge_door", 512.0, 400.0, "high")]), scaffold=False) as root:
        net = NetWorld(root)
    (made,) = net.defs["start"].doors
    assert made.world is net.defs["start"].proto.world is not None and made.level.mesh_entity_data == {"elevation": 0.0}
    based = door("base_door", 512.0, 200.0, "high")
    based["behaviour_config"]["SceneTransition"]["area_at"] = "base"
    with disposable_project(world_files(crossing, [based]), scaffold=False) as root:
        with pytest.raises(Unsupported, match="door 'base_door' stands on its base"):
            NetWorld(root)


def test_a_picture_door_fires_only_on_its_level(crossing: dict[str, bytes], monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    """Single-player's picture door (no area: its hit box; the authority refuses those): a 32 px door picture on the
    ground under the deck, its doorway its base, fires for a player standing on it under the deck and not for one at
    the same place on the deck."""
    import engine.optional_arcade as optional_arcade
    from engine.physics_model import entity_aabb

    monkeypatch.setattr(optional_arcade.arcade, "check_for_collision",
                        lambda a, b: entity_aabb(a).intersection(entity_aabb(b)) is not None)
    entity = door("door", 15.0 * M, 12.0 * M, "high", AREA)
    del entity["behaviour_config"]["SceneTransition"]["area_width"], entity["behaviour_config"]["SceneTransition"]["area_height"]
    with disposable_project(world_files(crossing, [entity]), scaffold=False) as root:
        world = single_player_world(root)[0]
    sprite = Picture(center_x=entity["x"], center_y=entity["y"], width=32.0, height=32.0, mesh_tag="door",
                     mesh_name="door", mesh_entity_data=entity)
    fired = {}
    for z in (0.0, 2.0 * M):
        hero = Picture(center_x=entity["x"], center_y=entity["y"], width=32.0, height=48.0, mesh_tag="player",
                       mesh_name="hero", mesh_entity_data={"elevation": z})
        requests: list[str] = []
        window = SimpleNamespace(scene_controller=SimpleNamespace(all_sprites=[hero]), hd2d_world=world,
                                 request_scene_change=requests.append, set_next_spawn_point=lambda _s: None,
                                 console_log=lambda _m: None)
        behaviour("SceneTransition")(sprite, window, **entity["behaviour_config"]["SceneTransition"]).update(1 / 60)
        fired[z] = requests == ["deck"]
    assert fired == {0.0: True, 2.0 * M: False}


def test_a_2d_room_s_door_fires_whatever_the_elevations() -> None:
    """No HD-2D World: a door saved 2 m up fires for a player at 0, in single-player (no ``hd2d_world``, or None) and
    in the authority (a 2D room's doors have no World), as before."""
    SceneTransition = behaviour("SceneTransition")
    entity = door("door", 100.0, 100.0, "high", AREA)
    entity["elevation"] = 2.0 * M
    for none in (False, True):
        actor = Picture(center_x=100.0, center_y=100.0, width=32.0, height=48.0, mesh_tag="player", mesh_name="hero",
                        mesh_entity_data={"elevation": 0.0})
        requests: list[str] = []
        window = SimpleNamespace(scene_controller=SimpleNamespace(all_sprites=[actor]),
                                 request_scene_change=requests.append, set_next_spawn_point=lambda _s: None,
                                 console_log=lambda _m: None)
        if none:
            window.hd2d_world = None
        sprite = Picture(center_x=100.0, center_y=100.0, width=32.0, height=32.0, mesh_tag="door", mesh_name="door",
                         mesh_entity_data=entity)
        SceneTransition(sprite, window, **entity["behaviour_config"]["SceneTransition"]).update(1 / 60)
        assert requests == ["deck"], none
    assert Door("d", "deck", "", 100.0, 100.0, AREA / 2, AREA / 2).touches(Body(100.0, 100.0, 32.0, 48.0, {"elevation": 0.0}))


def test_a_door_saved_at_0_on_ground_sculpted_up_since_is_on_that_ground() -> None:
    """A door Studio added at 0 before the ground under it was raised (a hill 2.5 m high, terrain anchoring settles
    nothing by itself) is on the ground as it now is, for a character standing beside it, in both runtimes; at its
    saved 0 it would be out of reach."""
    world = hill()
    top = ground_at(world, 16.0, 12.0)
    assert top > 2.0, "the hill's top"
    entity = door("door", 16.0 * M, 12.0 * M, "high", AREA)
    level = door_level(world, SimpleNamespace(center_x=16.0 * M, center_y=12.0 * M, width=AREA, height=AREA,
                                              mesh_entity_data=entity))
    assert abs(level.mesh_entity_data["elevation"] - top * M) < 0.01
    hero = Picture(center_x=16.0 * M, center_y=12.0 * M + FEET, width=32.0, height=48.0, mesh_tag="player",
                   mesh_name="hero", mesh_entity_data={"elevation": round(top * M, 3)})
    assert not same_level(world, SimpleNamespace(**{**vars(level), "mesh_entity_data": {"elevation": 0.0}}), hero)
    requests: list[str] = []
    window = SimpleNamespace(scene_controller=SimpleNamespace(all_sprites=[hero]), hd2d_world=world,
                             request_scene_change=requests.append, set_next_spawn_point=lambda _s: None,
                             console_log=lambda _m: None)
    sprite = Picture(center_x=16.0 * M, center_y=12.0 * M, width=32.0, height=32.0, mesh_tag="door", mesh_name="door",
                     mesh_entity_data=entity)
    behaviour("SceneTransition")(sprite, window, **entity["behaviour_config"]["SceneTransition"]).update(1 / 60)
    assert requests == ["deck"], "single-player"
    assert Door("d", "deck", "", 16.0 * M, 12.0 * M, AREA / 2, AREA / 2, world, level).touches(
        Body(hero.center_x, hero.center_y, 32.0, 48.0, hero.mesh_entity_data)), "the authority"


def test_the_starter_village_doors_still_fire(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The HD-2D template's two doors, single-player only (a picture door outside, saved at 0; a base-anchored area
    inside, saved 0.1 m up on the cottage's wooden floor), on the World the game builds: each fires for a player
    standing in its doorway, and each doorway is on the floor it was saved on. (A picture door's doorway is its base:
    its middle stands over the cottage behind it.)"""
    from PIL import Image

    import engine.optional_arcade as optional_arcade
    from engine.hd2d.glb import load_glb
    from engine.hd2d.settings import parse_hd2d
    from engine.physics_model import entity_aabb
    from engine.project_scaffold import create_project

    monkeypatch.setattr(optional_arcade.arcade, "check_for_collision",
                        lambda a, b: entity_aabb(a).intersection(entity_aabb(b)) is not None)
    root = tmp_path / "Village"
    create_project(root, "Village", "hd2d_rpg")
    SceneTransition = behaviour("SceneTransition")
    for rel in ("packs/core_regions/scenes/start.json", "packs/core_regions/scenes/cottage.json"):
        scene = json.loads((root / rel).read_text(encoding="utf-8"))
        hd = parse_hd2d(scene["settings"]["hd2d"])
        world = World(hd, {st.model: load_glb(root / st.model) for st in hd.structures})
        (entity,) = [e for e in scene["entities"] if e.get("tag") == "door"]
        with Image.open(root / entity["sprite"]) as picture:
            width, height = float(picture.width), float(picture.height)
        saved = float(entity.get("elevation") or 0.0)
        sprite = Picture(center_x=entity["x"], center_y=entity["y"], width=width, height=height, mesh_tag="door",
                         mesh_name="door", mesh_entity_data=entity)
        base = door_level(world, SimpleNamespace(center_x=sprite.center_x, center_y=sprite.bottom, width=width,
                                                 height=height, mesh_entity_data=entity))
        assert base.mesh_entity_data == {"elevation": saved}, rel
        hero = Picture(center_x=sprite.center_x, center_y=sprite.bottom + FEET - 4.0, width=32.0, height=48.0,
                       mesh_tag="player", mesh_name="hero", mesh_entity_data={"elevation": saved})
        requests: list[str] = []
        window = SimpleNamespace(scene_controller=SimpleNamespace(all_sprites=[hero]), hd2d_world=world,
                                 request_scene_change=requests.append, set_next_spawn_point=lambda _s: None,
                                 console_log=lambda _m: None)
        SceneTransition(sprite, window, **entity["behaviour_config"]["SceneTransition"]).update(1 / 60)
        assert len(requests) == 1, rel
