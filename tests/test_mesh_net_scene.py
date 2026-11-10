"""N6: a Studio-authored scene hosted by the graphics-free mesh_net authority (mesh_net.scene_room)."""

import asyncio
import json
import subprocess
import sys
from contextlib import AsyncExitStack

import pytest

from mesh_net import protocol as wire
from mesh_net.client import connect
from mesh_net.scene_room import COMBAT, COOP_FILES, COOP_SCENE, SPEED, SceneRoom, Unsupported, check_state, coop_files, disposable_project, parse_input
from mesh_net.server import Server

LEVER, GATE, BANDIT = "start_gate_lever_352_352_0_0", "start_gate_432_256_0_0", "start_bandit_608_256_0_0"


def make_room(files=None) -> SceneRoom:
    with disposable_project(files or coop_files(), scaffold=False) as root:
        return SceneRoom(root / COOP_SCENE, root)


class Driver:
    def __init__(self, room):
        self.room, self.seq = room, {}

    def send(self, eid, dx=0, dy=0, action=None, seq=None):
        self.seq[eid] = seq if seq is not None else self.seq.get(eid, 0) + 1
        msg = {"v": 1, "type": "input", "entity": eid, "seq": self.seq[eid], "dx": dx, "dy": dy}
        if action:
            msg["action"] = action
        self.room.input(eid, msg)

    def walk(self, eid, dx, dy, ticks):
        for _ in range(ticks):
            self.send(eid, dx, dy)
            self.room.step()

    def at(self, eid):
        b = self.room.players[eid].body
        return b.center_x, b.center_y

    def place(self, eid, x, y, facing=0):
        p = self.room.players[eid]
        p.body.center_x, p.body.center_y, p.facing = x, y, facing


@pytest.fixture(scope="module")
def room_factory():
    files = coop_files()
    return lambda: make_room(files)


@pytest.mark.integration
def test_committed_room_is_a_fresh_studio_build():
    sys.path.insert(0, "tooling")
    try:
        from make_coop_scene import build
    finally:
        sys.path.remove("tooling")
    files = coop_files()  # (compared as JSON: a Windows checkout may hold them with CRLF line ends)
    assert {rel: json.loads(text) for rel, text in build().items()} == {rel: json.loads(files[rel]) for rel in COOP_FILES}


@pytest.mark.fast
def test_authority_defaults_are_the_behaviours_own():
    from engine.behaviours.combat import Combat
    from engine.behaviours.player_controller import PlayerController
    from engine.behaviours.puzzle_behaviours import DoorLock
    from engine.interaction import DEFAULT_INTERACT_MAX_DIST

    assert SPEED == PlayerController.PARAM_DEFS["speed"].default
    assert COMBAT == {k: Combat.PARAM_DEFS[k].default for k in COMBAT}
    assert DoorLock.PARAM_DEFS["starts_locked"].default is True and DEFAULT_INTERACT_MAX_DIST == 72.0


@pytest.mark.integration
def test_authority_runs_without_graphics_or_studio():
    code = ("import sys; from mesh_net.scene_room import *; from mesh_net.server import Server\n"
            "with disposable_project(coop_files(), scaffold=False) as root: Server(SceneRoom(root / COOP_SCENE, root))\n"
            "bad = [k for k in ('arcade', 'pyglet', 'engine.game', 'engine.studio') if k in sys.modules]\n"
            "assert not bad, bad")
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True)


@pytest.mark.integration
def test_scene_identity_and_entity_mapping(room_factory):
    room = room_factory()
    with disposable_project(coop_files()) as root:  # what a client process has: a whole new Studio project
        client_view = SceneRoom(root / COOP_SCENE, root)
    assert room.identity == client_view.identity and len(room.identity) == 64
    assert (set(room.levers), set(room.doors), set(room.enemies)) == ({LEVER}, {GATE}, {BANDIT})
    assert room.template["id"] == "start_player_128_128_0_0" and room.spawn == (128.0, 256.0)
    assert room.step_px == SPEED / wire.HZ and room.cooldown == 10 and room.damage == 1.0
    assert len(room.scenery) == 88  # painted wall tiles; the gate and the bandit block through their own rules
    changed = coop_files()
    changed["assets/prefabs.json"] = changed["assets/prefabs.json"].replace(b'"cooldown": 0.5', b'"cooldown": 0.75')
    assert make_room(changed).identity != room.identity  # the player's shared definition is part of the room
    state = room.snapshot()
    check_state(state, room.identity)
    with pytest.raises(wire.Invalid, match="different scene"):
        check_state(state, "0" * 64)


@pytest.mark.integration
def test_movement_matches_the_engine_runtime(room_factory):
    """The authority's move() and engine.physics_runtime.move_entity_with_physics agree on the same colliders."""
    from types import SimpleNamespace

    from engine.physics_model import footprint
    from engine.physics_runtime import move_entity_with_physics

    room = room_factory()
    a = room.join()
    body = room.players[a].body
    twin = SimpleNamespace(center_x=body.center_x, center_y=body.center_y, width=body.width, height=body.height,
                           mesh_entity_data=body.mesh_entity_data, mesh_id="twin")
    d = Driver(room)
    for dx, dy, ticks in ((1, 0, 60), (0, 1, 30), (1, 1, 20), (-1, 0, 10), (0, -1, 60), (1, -1, 40)):
        for _ in range(ticks):
            solids = room.solids()
            d.send(a, dx, dy)
            room.step()
            p = room.players[a]
            move_entity_with_physics(twin, (p.dx * room.step_px, p.dy * room.step_px), solids)
            assert (twin.center_x, twin.center_y) == d.at(a)
    assert d.at(a)[0] + footprint(body.width, body.height)["w"] / 2 <= 416  # its feet never passed the wall, nor the gate


@pytest.mark.integration
def test_lever_opens_the_gate_once_for_everyone(room_factory):
    room = room_factory()
    d = Driver(room)
    a, b = room.join(), room.join()
    d.walk(a, 1, 0, 60)
    assert d.at(a)[0] == pytest.approx(390.5)  # stopped by the locked gate
    d.place(b, 100, 100)
    d.send(b, action="use")  # out of reach: nothing
    room.step()
    assert room.snapshot()["open"] == [] and room.snapshot()["used"] == []
    d.place(a, 352, 300)
    d.place(b, 330, 352)
    d.send(a, action="use")
    d.send(b, action="use")  # the same tick: one activation, the lever is one-shot
    room.step()
    state = room.snapshot()
    assert state["open"] == [GATE] and state["used"] == [LEVER]
    room.locked.add(GATE)  # (by hand: lock it again, so a second activation would show)
    d.send(b, action="use")
    room.step()
    assert room.snapshot()["open"] == []  # one-shot: the lever no longer works for anyone
    room.levers[LEVER][1]["one_shot"] = False  # the same room with a reusable lever: now it does...
    d.send(a, action="use", seq=d.seq[a])  # ...but not for a replayed frame (the same sequence number)
    room.step()
    assert room.snapshot()["open"] == []
    d.send(a, action="use")
    room.step()
    assert room.snapshot()["open"] == [GATE] and room.snapshot()["used"] == [LEVER]
    d.place(a, 380, 256)
    d.walk(a, 1, 0, 20)
    assert d.at(a)[0] > 440  # through the open gate
    with pytest.raises(wire.Invalid):
        room.input(b, {"v": 1, "type": "input", "entity": a, "seq": 99, "dx": 0, "dy": 0, "action": "use"})


@pytest.mark.integration
def test_disconnect_during_interaction_has_no_effect(room_factory):
    room = room_factory()
    d = Driver(room)
    a = room.join()
    d.place(a, 352, 330)
    d.send(a, action="use")
    character = room.leave(a)  # gone before the tick that would pull the lever
    room.step()
    assert room.snapshot()["open"] == [] and room.snapshot()["players"] == []
    back = room.join(character)
    room.step()
    assert room.snapshot()["open"] == [] and back != a
    d.send(back, action="use")
    room.step()
    assert room.snapshot()["open"] == [GATE]


@pytest.mark.integration
def test_two_players_defeat_the_bandit_and_one_takes_its_loot(room_factory):
    room = room_factory()
    d = Driver(room)
    a, b = room.join(), room.join()
    room.locked.clear()
    d.place(a, 560, 256, facing=0)  # left of the bandit, facing right
    d.place(b, 656, 256, facing=2)  # right of it, facing left
    d.place(room.join(), 300, 100)  # a third player out of reach
    d.send(a, action="attack")
    room.step()
    assert room.snapshot()["enemies"] == [[BANDIT, 2.0]]
    d.send(a, action="attack")  # inside the 10-tick cooldown: no damage
    room.step()
    d.send(3, action="attack")  # out of reach
    room.step()
    assert room.snapshot()["enemies"] == [[BANDIT, 2.0]]
    d.send(b, action="attack")
    room.step()
    for _ in range(10):
        room.step()
    d.send(a, action="attack")
    d.send(b, action="attack")  # one tick, two hits: the second finds it dead
    room.step()
    state = room.snapshot()
    assert state["enemies"] == [[BANDIT, 0.0]] and state["drops"] == [BANDIT] and state["loot"] == []
    d.walk(a, 1, 0, 10)  # the dead bandit no longer blocks
    assert d.at(a)[0] > 600
    d.send(b, action="take")
    d.send(a, action="take")  # a race: entity order decides, the loot exists once
    room.step()
    state = room.snapshot()
    assert state["drops"] == [] and state["loot"] == [[BANDIT, a]]
    character = room.leave(a)
    assert room.snapshot()["loot"] == [[BANDIT, None]]  # held offline
    back = room.join(character)
    assert room.snapshot()["loot"] == [[BANDIT, back]]
    assert room.enemies[BANDIT].loot == [{"item_id": None, "gold": 10, "quantity": 1}]


@pytest.mark.fast
def test_inputs_and_snapshots_are_validated():
    good = {"v": 1, "type": "input", "entity": 3, "seq": 1, "dx": 1, "dy": -1, "action": "use"}
    assert parse_input(good, 3) == (1, 1, -1, "use")
    for bad in ({**good, "dx": 2}, {**good, "action": "teleport"}, {**good, "entity": 4}, {**good, "seq": 0},
                {**good, "x": 5}, {**good, "dx": 1.0}):
        with pytest.raises(wire.Invalid):
            parse_input(bad, 3)
    state = {"v": 1, "type": "scene_state", "tick": 1, "scene": "a" * 64, "players": [[1, 2.5, 3, 0]],
             "open": [], "used": [], "enemies": [["e", 3.0]], "drops": [], "loot": [["e", 1]]}
    check_state(state)
    for bad in ({"players": [[1, 2, 3, 4]]}, {"players": [[1, 2, 3, 0], [1, 2, 3, 0]]}, {"loot": [["e", 2]]},
                {"enemies": [["e", -1]]}, {"players": [[1, float("inf"), 3, 0]]}, {"open": [3]}):
        with pytest.raises(wire.Invalid):
            check_state({**state, **bad})


@pytest.mark.integration
def test_unsupported_scenes_are_refused(room_factory):
    def edited(change):
        files = coop_files()
        scene = json.loads(files[COOP_SCENE])
        change(scene)
        files[COOP_SCENE] = json.dumps(scene).encode()
        return files

    def hd2d(scene):
        scene.setdefault("settings", {})["hd2d"] = {"enabled": True}

    def map_file_walls(scene):
        for layer in scene["tilemap"]["tile_layers"]:
            layer.pop("tiles")

    def second_player(scene):
        scene["entities"].append({"id": "p2", "prefab_id": "player", "x": 1, "y": 1})

    def bare_solid(scene):
        scene["entities"].append({"id": "rock", "x": 1, "y": 1, "solid": True})

    def empty_hd2d(scene):
        scene.setdefault("settings", {})["hd2d"] = {}

    def flag_gated(scene):
        scene["entities"][1]["require_flags"] = ["met_the_guard"]

    def sizeless_collider(scene):
        scene["entities"][0]["components"] = {"collider": {"kind": "box"}}  # Arcade's picture hit box in single-player

    def long_ids(scene):
        for n in range(29):  # 32 networked objects in all: the count is allowed, their ids are too long
            scene["entities"].append({**scene["entities"][3], "id": f"bandit_{n}_" + "x" * 200, "name": f"B{n}"})

    for change, message in ((hd2d, "HD-2D"), (empty_hd2d, "HD-2D"), (map_file_walls, "inline tiles"),
                            (second_player, "exactly one"), (bare_solid, "needs a picture"), (flag_gated, "game flags"),
                            (sizeless_collider, "sized box"), (long_ids, "one frame")):
        with pytest.raises(Unsupported, match=message):
            make_room(edited(change))


@pytest.mark.integration
def test_two_clients_share_the_scene_over_sockets_and_resume(room_factory):
    room = room_factory()

    async def run():
        server = Server(room)
        port = await server.start()
        checks = {"check": lambda m: check_state(m, room.identity), "check_input": parse_input}

        async def until(client, predicate):
            async with asyncio.timeout(5):
                while not predicate(await client.receive()):
                    pass

        try:
            async with AsyncExitStack() as stack:
                a = await stack.enter_async_context(connect(port, **checks))
                b = await stack.enter_async_context(connect(port, **checks))
                await until(a, lambda s: len(s["players"]) == 2)
                for _ in range(5):
                    await a.input(1, 0)
                    await b.input(0, 1)
                await until(b, lambda s: dict((r[0], r[1:3]) for r in s["players"])[a.entity][0] > 128
                            and dict((r[0], r[1:3]) for r in s["players"])[b.entity][1] > 256)
                await b.input(0, 0)
                await until(a, lambda s: True)
                token, gone = b.resume, b.entity
                b.writer.close()
                await until(a, lambda s: [r[0] for r in s["players"]] == [a.entity])
                saved = room.snapshot()
                async with connect(port, token, **checks) as again:
                    assert again.entity != gone and again.resume != token
                    rows = {r[0]: r for r in again.state["players"]}
                    assert set(rows) == {a.entity, again.entity}  # no ghost of the old session, no duplicate
                    assert len(room.players) == 2 and saved["tick"] <= again.state["tick"]
                with pytest.raises((wire.Invalid, EOFError)):  # a spent credential cannot be replayed: the server hangs up
                    async with connect(port, token, **checks):
                        pass
        finally:
            await server.close()

    asyncio.run(run())


@pytest.mark.integration
def test_the_co_op_room_is_an_ordinary_single_player_scene():
    """Nothing in it is multiplayer-specific: the engine's own strict loader keeps every object and behaviour, and the
    shared player resolves with its controls, camera, animation and Combat."""
    from engine.scene_loader import SceneLoader

    with disposable_project(coop_files()) as root:
        scene = SceneLoader().load_scene(str(root / COOP_SCENE), strict=True)
    assert [e["id"] for e in scene["entities"]] == ["start_player_128_128_0_0", LEVER, GATE, BANDIT]
    player = scene["entities"][0]
    assert [b["type"] for b in player["behaviours"]] == ["PlayerController", "CameraFollow", "Animator", "Combat"]


@pytest.mark.integration
def test_replayed_frames_never_steer_or_act(room_factory):
    room = room_factory()
    d = Driver(room)
    a = room.join()
    d.send(a, 0, 1)
    room.step()
    y = d.at(a)[1]
    d.send(a, 0, -1, action="attack", seq=d.seq[a])  # the same sequence number again, another direction
    room.step()
    assert d.at(a)[1] == y + room.step_px and room.players[a].attack_after == 0  # still the first frame's walk


@pytest.mark.integration
def test_a_lever_behind_the_player_is_out_of_reach_as_in_single_player(room_factory):
    room = room_factory()
    d = Driver(room)
    a = room.join()
    d.place(a, 352, 420, facing=1)  # 68 px above the lever, facing up: behind it, beyond contact distance
    d.send(a, action="use")
    room.step()
    assert room.snapshot()["open"] == []
    room.players[a].facing = 3  # facing down at it
    d.send(a, action="use")
    room.step()
    assert room.snapshot()["open"] == [GATE]


@pytest.mark.integration
def test_positions_stay_inside_what_clients_accept(room_factory):
    from mesh_net.scene_room import BOUND

    room = room_factory()
    d = Driver(room)
    a = room.join()
    d.place(a, BOUND - 1, BOUND - 1)
    d.walk(a, 1, 1, 3)
    assert d.at(a) == (BOUND, BOUND)
    check_state(room.snapshot(), room.identity)


@pytest.mark.integration
def test_an_invulnerable_enemy_takes_no_damage():
    files = coop_files()
    scene = json.loads(files[COOP_SCENE])
    bandit = next(e for e in scene["entities"] if e["id"] == BANDIT)
    bandit["behaviour_config"]["Health"]["invulnerable"] = True
    files[COOP_SCENE] = json.dumps(scene).encode()
    room = make_room(files)
    d = Driver(room)
    a = room.join()
    room.locked.clear()
    d.place(a, 560, 256, facing=0)
    d.send(a, action="attack")
    room.step()
    assert room.snapshot()["enemies"] == [[BANDIT, 3.0]]


@pytest.mark.fast
def test_drops_roll_as_droptable_rolls_them():
    """Same seed, same table: the authority's loot is what engine.behaviours.drop_table.DropTable gives."""
    from types import SimpleNamespace

    from engine.behaviours.drop_table import DropTable
    from mesh_net.scene_room import roll_drops

    tables = [{"seed": 7, "drops": [{"chance": 0.5, "gold": 1}, {"chance": 0.5, "gold": 2}, {"chance": 0.5, "gold": 3}]},
              {"seed": 3, "drops": [{"chance": 0, "item_id": "a"},
                                    {"chance": 0.3, "item_id": "b", "min_quantity": 2, "max_quantity": 5},
                                    {"gold": 4}]}]
    for cfg in tables:
        table = DropTable(SimpleNamespace(), SimpleNamespace(event_bus=None), **cfg)
        given = []
        table._apply_drop = lambda drop, qty, given=given: given.append(
            {"item_id": drop["item_id"], "gold": drop["gold"], "quantity": qty})
        table.match_self = False
        table._on_event(SimpleNamespace(payload={}))
        assert given and roll_drops(cfg) == given


@pytest.mark.integration
def test_server_tiles_are_the_engines_tiles():
    """engine.tilemap's collision sprites (built headless, as a window builds them) against the authority's, for the
    co-op room and for map edits the engine handles in its own way; what the authority can't mirror is refused."""
    from types import SimpleNamespace

    from engine.assets import AssetManager
    from engine.scene_loader import SceneLoader
    from engine.scene_runtime.scene_load_apply import load_tilemap_layers
    from engine.tilemap import TilemapManager
    from mesh_net.scene_room import load_scene, tile_bodies

    def compare(edit_scene=None, edit_files=None):
        files = coop_files()
        scene = json.loads(files[COOP_SCENE])
        if edit_scene:
            edit_scene(scene)
        files[COOP_SCENE] = json.dumps(scene).encode()
        with disposable_project(files) as root:
            if edit_files:
                edit_files(root)
            path = root / COOP_SCENE
            manager = TilemapManager(AssetManager())
            ctl = SimpleNamespace(window=SimpleNamespace(tilemap_manager=manager), solid_sprites=[],
                                  navigation=SimpleNamespace(invalidate=lambda: None),
                                  _init_tilemap_batching=lambda *a: None, _apply_tilemap_world_bounds=lambda *a: None)
            load_tilemap_layers(ctl, SceneLoader().load_scene(str(path)), path.parent, load_tilemap_func=manager.load_map)
            engine = sorted((s.center_x, s.center_y, s.width, s.height) for s in ctl.solid_sprites)
            try:
                bodies = tile_bodies(load_scene(path)[1], path.parent)
            except Unsupported as exc:
                return engine, str(exc)
        return engine, sorted((b.center_x, b.center_y, b.width, b.height) for b in bodies)

    def walls(scene):
        return next(layer for layer in scene["tilemap"]["tile_layers"] if layer["id"] == "walls")

    def unknown_tile(scene):
        tiles = walls(scene)["tiles"]
        tiles[tiles.index(9)] = 5000

    def small_tiles(root):
        path = root / "assets/tilesets/starter.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["tilewidth"] = data["tileheight"] = 16
        path.write_text(json.dumps(data), encoding="utf-8")

    engine, ours = compare()
    assert len(engine) == 88 and ours == engine
    engine, ours = compare(edit_scene=unknown_tile)
    assert ours == engine and len(engine) == 87
    engine, ours = compare(edit_files=small_tiles)
    assert ours == engine and engine[0][2] == 16
    engine, refused = compare(edit_files=lambda root: (root / "assets/tilesets/starter.json").unlink())
    assert engine == [] and "cannot be read" in refused


@pytest.mark.integration
def test_identity_covers_what_shapes_collision(room_factory):
    """A different map file changes the room's collision, so it changes the identity too."""
    room = room_factory()
    files = coop_files()
    data = json.loads(files["packs/core_regions/maps/start.json"])
    next(layer for layer in data["layers"] if layer.get("name") == "walls")["offsetx"] = 64
    files["packs/core_regions/maps/start.json"] = json.dumps(data).encode()
    moved = make_room(files)
    assert moved.identity != room.identity and moved.scenery[0].center_x == room.scenery[0].center_x + 64
