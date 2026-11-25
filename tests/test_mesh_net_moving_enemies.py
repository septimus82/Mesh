"""M4-4 (owner decision OD7): server-authoritative moving enemies through one shared, graphics-free model.

- An enemy walking a ``FloorRoute`` in an HD-2D room walks it on the authority each tick (N6, and so every N7
  instance), through engine.hd2d.route.FloorRoute: the model single-player's behaviour is an adapter over
  (tests/test_floor_route_model.py pins that behaviour to its traces from before the extraction). Single-player and the
  authority trace the same walk at equal deltas, over the crossing's stairs and its bridge.
- Its row carries where it is now (x, y, elevation, floor), which a client's checks accept every tick; hits and
  blocking are judged there, never where it was.
- What the authority can't reproduce is refused at load: an enemy moving by another behaviour, a solid that moves, an
  enemy whose route starts where it can't stand.
- The window shows enemies as it shows peers (Playback, two ticks behind; never predicted), and predicts its own avatar
  against them where the snapshot put them.
"""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace
from typing import Any

import pytest

from engine.hd2d.route import FloorRoute
from mesh_net import protocol as wire
from mesh_net import scene_room
from mesh_net.playback import Playback
from mesh_net.scene_room import COOP_SCENE, SceneRoom, Unsupported, check_state, coop_files, disposable_project
from tests.test_floor_route_model import Walker, crossing, walker
from tooling.m4_latency_probe import BANDIT, crossing_files

pytestmark = pytest.mark.integration  # (builds projects in folders, loads rooms from files)

SCENE = "packs/core_regions/scenes/start.json"
DT = 1 / wire.HZ  # single-player's fixed frame here: the authority's tick
# The crossing walked end to end: from the east platform (2 m up) over the bridge to the west platform, down the west
# stairs to the ground, and back up the east stairs (feet points, px; elevation px).
ROUTE = {"route": [[320.0, 400.0, 64.0], [320.0, 120.0, 0.0], [784.0, 336.0, 64.0]], "speed": 70.0, "wait": 0.5}
START = (784.0, 336.0 + 18.0, 64.0)  # the bandit's sprite centre and elevation: on the east platform (the warden's)


def bandit(x: float, y: float, elevation: float = 0.0, route: dict[str, Any] | None = None, **changes: Any) -> dict[str, Any]:
    """The co-op room's bandit (an enemy: Health, DropTable, solid) at (x, y) px, walking ``route`` (FloorRoute)."""
    entity = copy.deepcopy(next(e for e in json.loads(coop_files()[COOP_SCENE])["entities"] if e["id"] == BANDIT))
    entity.update(x=x, y=y, elevation=elevation, **changes)
    if route is not None:
        entity["behaviours"] = [*entity["behaviours"], "FloorRoute"]
        entity["behaviour_config"]["FloorRoute"] = copy.deepcopy(route)
    return entity


def with_entities(files: dict[str, bytes], *entities: dict[str, Any], rel: str = SCENE) -> dict[str, bytes]:
    scene = json.loads(files[rel])
    scene["entities"] += list(entities)
    return {**files, rel: json.dumps(scene).encode()}


@pytest.fixture(scope="module")
def files() -> dict[str, bytes]:
    return crossing_files()


def room_of(files: dict[str, bytes], rel: str = SCENE) -> SceneRoom:
    with disposable_project(files, scaffold=False) as root:
        return SceneRoom(root / rel, root)


@pytest.fixture(scope="module")
def routed(files: dict[str, bytes]) -> dict[str, bytes]:
    return with_entities(files, bandit(*START, route=ROUTE))


Row = tuple[float, float, float, "str | None"]


def row(body: Any) -> Row:
    return body.center_x, body.center_y, body.mesh_entity_data.get("elevation", 0.0), getattr(body, "mesh_hd2d_floor", None)


def single_player(files: dict[str, bytes], ticks: int) -> list[Row]:
    """Single-player's FloorRoute behaviour (the adapter: the game's Arcade sweep) moving the bandit's sprite through
    the World the game builds, a solid sprite of its own window as the game has it, at DT."""
    with disposable_project(files, scaffold=False) as root:
        world, _warden, _size, _solids = crossing(root)
        from engine.scene_loader import SceneLoader
        from mesh_net.scene_room import picture_size

        entities = SceneLoader().load_scene(str(root / SCENE))["entities"]
        entity = next(e for e in entities if e["id"] == BANDIT)
        size = picture_size(entity, root)
        assert size is not None
        sprite = walker(entity, size)
        solids = [sprite if e is entity else walker(e, (0.0, 0.0)) for e in entities if e.get("solid")]
        from engine.behaviours.floor_route import FloorRouteBehaviour

        window = SimpleNamespace(hd2d_world=world, scene_controller=SimpleNamespace(solid_sprites=solids))
        behaviour = FloorRouteBehaviour(sprite, window, **entity["behaviour_config"]["FloorRoute"])
        trace = []
        for _ in range(ticks):
            behaviour.update(DT)
            trace.append(row(sprite))
        return trace


def authority(room: SceneRoom, ticks: int) -> list[Row]:
    trace = []
    for _ in range(ticks):
        room.step()
        trace.append(row(room.enemies[BANDIT].body))
    return trace


def test_single_player_and_the_authority_walk_one_floor_route_alike_over_stairs_and_the_bridge(
        routed: dict[str, bytes]) -> None:
    ticks = 1400
    single, served = single_player(routed, ticks), authority(room_of(routed), ticks)
    for tick, (a, b) in enumerate(zip(single, served)):
        assert abs(a[0] - b[0]) <= 1e-6 and abs(a[1] - b[1]) <= 1e-6, f"tick {tick}: x/y {a[:2]} != {b[:2]}"
        assert a[2:] == b[2:], f"tick {tick}: (elevation, floor) {a[2:]} != {b[2:]}"
    floors = [r[3] for r in served]
    changes = [b for a, b in zip(floors, floors[1:]) if a != b]
    assert {"crossing/col_bridge_deck", "crossing/col_stairs_west", "crossing/col_stairs_east", "ground",
            "crossing/col_platform_west", "crossing/col_platform_east"} <= set(changes), changes
    assert sum(1 for a, b in zip(served, served[1:]) if a[:2] == b[:2]) >= 10, "and it waits at its points"


def test_in_a_2d_room_floor_route_moves_nothing_in_either() -> None:
    """Single-player's FloorRoute does nothing without HD-2D floors; nor does the authority (no route is made)."""
    files = coop_files()
    scene = json.loads(files[COOP_SCENE])
    entity = next(e for e in scene["entities"] if e["id"] == BANDIT)
    entity["behaviours"].append("FloorRoute")
    entity["behaviour_config"]["FloorRoute"] = {"route": [[100.0, 100.0], [400.0, 300.0]], "speed": 70.0}
    room = room_of({**files, COOP_SCENE: json.dumps(scene).encode()}, COOP_SCENE)
    body = room.enemies[BANDIT].body
    assert room.enemies[BANDIT].route is None
    start = (body.center_x, body.center_y)
    for _ in range(40):
        room.step()
    assert (body.center_x, body.center_y) == start and room.snapshot()["enemies"][0][3:5] == list(start)
    from engine.behaviours.floor_route import FloorRouteBehaviour

    sprite = Walker(center_x=start[0], center_y=start[1], width=32.0, height=48.0, scale_x=1.0, mesh_entity_data=entity)
    behaviour = FloorRouteBehaviour(sprite, SimpleNamespace(hd2d_world=None, scene_controller=None),
                                    **entity["behaviour_config"]["FloorRoute"])
    for _ in range(40):
        behaviour.update(DT)
    assert (sprite.center_x, sprite.center_y) == start


def test_both_runtimes_run_the_one_shared_model(routed: dict[str, bytes], monkeypatch: pytest.MonkeyPatch) -> None:
    """The behaviour and the authority both call engine.hd2d.route.FloorRoute.update; the authority gives it its
    Arcade-free sweep (mesh_net.scene_room.move), single-player the game's (None)."""
    calls: list[tuple[str, Any]] = []
    original = FloorRoute.update

    def spy(self: FloorRoute, world: Any, body: Any, dt: float, solids: Any = None, sweep: Any = None) -> None:
        calls.append((type(body).__name__, sweep))
        original(self, world, body, dt, solids, sweep)

    monkeypatch.setattr(FloorRoute, "update", spy)
    single_player(routed, 1)
    room_of(routed).step()
    assert calls == [("Walker", None), ("Body", scene_room.move)]


def test_each_tick_the_authority_walks_it_a_step_and_its_row_carries_where_it_is(routed: dict[str, bytes]) -> None:
    """Every tick: at most speed/HZ in x/y (no teleport), its row is its body (x/y to the wire's 0.01 px, elevation,
    floor), and a client's own room accepts the snapshot (check_state: the floor under it, even at a floor's edge)."""
    room, client = room_of(routed), room_of(routed)
    eid = room.join()
    body = room.enemies[BANDIT].body
    moved = 0
    for _ in range(900):
        before = (body.center_x, body.center_y)
        room.step()
        step = ((body.center_x - before[0]) ** 2 + (body.center_y - before[1]) ** 2) ** 0.5
        assert step <= 70.0 / wire.HZ + 1e-9
        moved += step > 0
        state = room.snapshot()
        r = next(r for r in state["enemies"] if r[0] == BANDIT)
        assert r[3:] == [round(body.center_x, 2), round(body.center_y, 2), *room.level(body)]
        assert r[6] is not None
        check_state(state, client.identity, client)
    assert moved > 600, "it walked"
    room.leave(eid)


def test_a_dead_enemy_stops_walking(routed: dict[str, bytes]) -> None:
    room = room_of(routed)
    for _ in range(30):
        room.step()
    enemy = room.enemies[BANDIT]
    enemy.state = type(enemy.state)(hp=0.0, max_hp=enemy.state.max_hp, dead=True)
    assert enemy.state.dead
    at = row(enemy.body)
    for _ in range(30):
        room.step()
    assert row(enemy.body) == at


def test_every_n7_instance_walks_its_own_enemies(routed: dict[str, bytes], monkeypatch: pytest.MonkeyPatch) -> None:
    """N7: each instance is the room's own copy (mesh_net.world.World._create), stepped by the world's tick; each
    walks its enemy, on its own (one killed there leaves the other walking). (A party's instance with no member in it
    would end in the tick: kept here.)"""
    from mesh_net.world import WORLD_FILE, World

    files = {**routed, WORLD_FILE: json.dumps({"id": "main", "start_scene": "start",
                                               "scenes": {"start": {"path": SCENE}}}).encode()}
    with disposable_project(files, scaffold=False) as root:
        world = World(root)
    monkeypatch.setattr(world, "_cleanup", lambda: None)
    party = world._create("start", 7)
    hub = world.hub
    for _ in range(20):
        world.step()
    a, b = hub.room.enemies[BANDIT], party.room.enemies[BANDIT]
    assert a is not b and a.body is not b.body and a.route is not b.route
    assert row(a.body) == row(b.body) and row(a.body)[:2] != START[:2], "both walked, alike"
    b.state = type(b.state)(hp=0.0, max_hp=b.state.max_hp, dead=True)
    there = row(b.body)
    for _ in range(20):
        world.step()
    assert row(b.body) == there and row(a.body) != there, "the hub's walks on"


def test_a_hit_on_a_moving_enemy_is_judged_where_it_is_now(routed: dict[str, bytes]) -> None:
    """The attack's hitbox is made where the attacker stands, on the tick the server reads it, against the enemy where
    it has just walked that tick (owner condition 4: current server geometry, never a past position): a hitbox that
    overlaps its feet box after this tick's walk by half a step, but not before it, hits on that tick; one where it
    stood 20 ticks ago misses."""
    from engine.physics_model import entity_aabb

    room = room_of(routed)
    for _ in range(60):  # (off the east platform's middle, walking west along it)
        room.step()
    enemy = room.enemies[BANDIT]
    long_ago = (enemy.body.center_x, enemy.body.center_y)
    for _ in range(20):
        room.step()
    before = entity_aabb(enemy.body)
    twin = copy.deepcopy(room, {id(room.world): room.world})
    twin.step()
    after = entity_aabb(twin.enemies[BANDIT].body)
    dx = after.x - before.x
    assert after.y == before.y and abs(dx) > 1.0, "walking along x this tick"
    side = 1.0 if dx > 0 else -1.0
    near = after.x + side * (after.w / 2 - abs(dx) / 2)  # (the hitbox's edge: half a step into where its feet are now)
    centre = near + side * room.hitbox / 2
    assert abs(centre - after.x) < (room.hitbox + after.w) / 2 <= abs(centre - before.x), "overlaps now, not before"

    def swing_at(x: float, y: float) -> bool:
        """An attack read on the next tick by a player facing east whose hitbox is centred at (x, y) px."""
        trial = copy.deepcopy(room, {id(room.world): room.world})
        eid = trial.join()
        p = trial.players[eid]
        p.body.center_x, p.body.center_y, p.facing = x - trial.reach, y, 0
        p.body.mesh_entity_data["elevation"] = trial.enemies[BANDIT].body.mesh_entity_data["elevation"]
        trial.input(eid, wire.input_frame(eid, 1, 0, 0, trial.tick + 1, "attack"))
        trial.step()
        return trial.enemies[BANDIT].hit_seq == 1

    then = entity_aabb(scene_room.Body(*long_ago, enemy.body.width, enemy.body.height, enemy.body.mesh_entity_data))
    assert abs(then.x - after.x) > 48, "well away from there"
    assert not swing_at(then.x, then.y), "where it was 20 ticks ago: a miss"
    assert swing_at(centre, after.y), "where it is after this tick's walk: a hit, on this tick"


@pytest.mark.parametrize("case", ["enemy patrol", "enemy wander", "solid patrol", "solid floor route",
                                  "enemy can't stand"])
def test_movers_the_authority_cant_reproduce_are_refused_at_load(files: dict[str, bytes], case: str) -> None:
    entity = {
        "enemy patrol": bandit(560.0, 122.0, behaviours=["Animator", "Health", "Patrol"]),
        "enemy wander": bandit(560.0, 122.0, behaviours=["Animator", "Health", "DropTable", "Wander"]),
        "solid patrol": {"id": "post", "x": 560.0, "y": 122.0, "solid": True, "behaviours": ["Patrol"],
                         "components": {"collider": {"kind": "box", "w": 16, "h": 16}}},
        "solid floor route": {"id": "post", "x": 560.0, "y": 122.0, "solid": True, "behaviours": ["FloorRoute"],
                              "behaviour_config": {"FloorRoute": {"route": [[600.0, 104.0, 0.0]]}},
                              "components": {"collider": {"kind": "box", "w": 16, "h": 16}}},
        "enemy can't stand": bandit(560.0, 122.0, elevation=64.0, route={"route": [[600.0, 104.0, 0.0]]}),
    }[case]
    expected = {"enemy patrol": "the enemy .* moves by Patrol", "enemy wander": "the enemy .* moves by Wander",
                "solid patrol": "the solid 'post' moves by Patrol", "solid floor route": "the solid 'post' moves by FloorRoute",
                "enemy can't stand": "walks a FloorRoute but can't stand where it is"}[case]
    with pytest.raises(Unsupported, match=expected):
        room_of(with_entities(files, entity))


def test_movers_that_change_nothing_on_the_server_still_load(files: dict[str, bytes]) -> None:
    """A non-solid character walking (it blocks nothing: the window stands it still) and a FloorRoute enemy in a 2D
    room (which moves nowhere in either runtime) load."""
    villager = {"id": "walker", "x": 560.0, "y": 122.0, "behaviours": ["Wander"], "sprite": "assets/sprites/starter_villager.png"}
    assert room_of(with_entities(files, villager)).enemies == {}
    coop = coop_files()
    scene = json.loads(coop[COOP_SCENE])
    next(e for e in scene["entities"] if e["id"] == BANDIT)["behaviours"].append("FloorRoute")
    assert BANDIT in room_of({**coop, COOP_SCENE: json.dumps(scene).encode()}, COOP_SCENE).enemies


def test_the_prediction_blocks_on_enemies_where_the_snapshot_puts_them(routed: dict[str, bytes]) -> None:
    """SceneRoom.solids(state) (a client's prediction): each live solid enemy where its row is (x, y, elevation,
    floor), not where its scene put it."""
    server, client = room_of(routed), room_of(routed)
    for _ in range(80):
        server.step()
    state = server.snapshot()
    r = next(r for r in state["enemies"] if r[0] == BANDIT)
    placed = [b for b in client.solids(state) if b.mesh_entity_data.get("id") == BANDIT]
    assert [(b.center_x, b.center_y, b.mesh_entity_data["elevation"], b.mesh_hd2d_floor) for b in placed] == [tuple(r[3:])]
    assert (r[3], r[4]) != (START[0], START[1])
    dead = {**state, "enemies": [[*r[:1], 0, *r[2:]]]}
    assert not [b for b in client.solids(dead) if b.mesh_entity_data.get("id") == BANDIT], "a dead one blocks nothing"


def test_playback_shows_enemies_two_ticks_behind_interpolated() -> None:
    def state(tick: int, x: float, z: float, floor: str) -> dict[str, Any]:
        return {"tick": tick, "players": [], "enemies": [["e", 3.0, 0, x, 10.0, z, floor]]}

    playback = Playback(lambda s: None)
    for tick in range(1, 5):
        playback.push(state(tick, 10.0 * tick, 4.0 * tick, f"f{tick}"), tick / wire.HZ)
    now = 4 / wire.HZ
    assert playback.enemies(now) == {"e": (20.0, 10.0, 8.0, "f2")}, "two ticks behind the latest (tick 4)"
    half = playback.enemies(now + 0.5 / wire.HZ)
    assert half["e"][:3] == pytest.approx((25.0, 10.0, 10.0)) and half["e"][3] == "f3", "between, the nearer's floor"
    assert playback.positions(now + 0.5 / wire.HZ) == {}, "players and enemies share one cursor"
    assert Playback(lambda s: None).enemies(0.0) == {}


def test_the_window_places_enemies_where_playback_shows_them() -> None:
    """SceneView.sync puts each enemy's sprite at the position given (x, y; in HD-2D its elevation and floor), its
    Animator walking by how far it moved, as it places peers."""
    from mesh_net.scene_client import SceneView

    sprite = SimpleNamespace(center_x=0.0, center_y=0.0, mesh_entity_data={"elevation": 0.0}, mesh_hd2d_floor=None,
                             visible=True, color=(1, 2, 3))
    view = object.__new__(SceneView)
    view.flashes, view.avatars, view.sprites, view.drops, view.doors, view.levers = {}, {}, {"e": sprite}, {}, [], []
    view.room = SimpleNamespace(world=object())
    view.window = SimpleNamespace()
    view.sync(None, {}, None, 0.1, {"e": (10.0, 20.0, 32.0, "deck")})
    assert (sprite.center_x, sprite.center_y, sprite.mesh_entity_data["elevation"], sprite.mesh_hd2d_floor) == (
        10.0, 20.0, 32.0, "deck")
    assert (sprite.mesh_velocity_x, sprite.mesh_velocity_y) == pytest.approx((100.0, 200.0))


def test_an_enemy_row_rounded_over_a_floors_edge_is_accepted(routed: dict[str, bytes]) -> None:
    """A walking enemy's row is its x/y to 0.01 px. One whose feet stand on the west stairs' east edge (11 m) can be
    sent 0.004 px beyond it: the client's check samples the rounding's corners, as for players (floor_under), and
    accepts it; a whole pixel beyond is refused."""
    room = room_of(routed)
    state = room.snapshot()

    def row_at(x: float) -> dict[str, Any]:
        r = next(r for r in state["enemies"] if r[0] == BANDIT)
        return {**state, "enemies": [[r[0], r[1], r[2], x, 200.0 + 18.0, 28.0, "crossing/col_stairs_west"]]}

    check_state(row_at(352.0 - 1.0), room.identity, room)
    check_state(row_at(352.004), room.identity, room)
    with pytest.raises(wire.Invalid, match="not under it"):
        check_state(row_at(353.0), room.identity, room)
