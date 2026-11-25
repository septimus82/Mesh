"""HD-2D online M1-A-2: the graphics-free authority (mesh_net.scene_room / mesh_net.world) runs HD-2D floors on the one
collision world single-player builds (engine.hd2d.world.build_world + World.move, its own Arcade-free sweep), refuses
only where it would differ from single-player, keeps single-player's arrival rule, and a client whose collision world
differs (its files, or its window's own build) is refused before it plays the room.

M3-2 (wire v2): snapshot rows carry each body's elevation and floor, clients place avatars there and refuse rows their
own collision world contradicts, and no client frame can place a body.

The room is the floors demo's stone crossing (tooling/hd2d_floors_demo.py build): ground, stairs, two platforms 2 m up
and a bridge between them over an underpass."""

from __future__ import annotations

import asyncio
import hashlib
import json
import struct
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest

from engine.physics_model import entity_aabb
from mesh_net import protocol as wire
from mesh_net.client import connect
from mesh_net.scene_client import JoinRefused, SceneView, check_window_world
from mesh_net.scene_room import (
    COOP_SCENE,
    Feedback,
    Player,
    Prediction,
    SceneRoom,
    Unsupported,
    check_state,
    coop_files,
    disposable_project,
    load_scene,
)
from mesh_net.server import Server
from mesh_net.world import WORLD_FILE, World, check_welcome, welcome

pytestmark = pytest.mark.integration  # (builds projects in folders, loads rooms from files)

REPO = Path(__file__).resolve().parents[1]
SCENE = "packs/core_regions/scenes/start.json"
DECK_SCENE = "packs/core_regions/scenes/deck.json"
MODEL = "assets/models/stone_crossing.glb"


@pytest.fixture(scope="module")
def crossing(tmp_path_factory: pytest.TempPathFactory) -> dict[str, bytes]:
    """The floors demo's project, as files."""
    sys.path.insert(0, str(REPO / "tooling"))
    try:
        import hd2d_floors_demo
    finally:
        sys.path.remove(str(REPO / "tooling"))
    project = hd2d_floors_demo.build(tmp_path_factory.mktemp("crossing") / "proj")
    return {p.relative_to(project).as_posix(): p.read_bytes() for p in project.rglob("*") if p.is_file()}


def edited(files: dict[str, bytes], change: Callable[[dict[str, Any]], None], rel: str = SCENE) -> dict[str, bytes]:
    scene = json.loads(files[rel])
    change(scene)
    return {**files, rel: json.dumps(scene).encode()}


def make_room(files: dict[str, bytes]) -> SceneRoom:
    with disposable_project(files, scaffold=False) as root:
        return SceneRoom(root / SCENE, root)


def raised_deck(glb: bytes, by: float = 0.5) -> bytes:
    """The crossing's model with its bridge deck collider ``by`` m higher (the art unchanged)."""
    length = struct.unpack("<I", glb[12:16])[0]
    doc = json.loads(glb[20:20 + length])
    rest = glb[20 + length:]
    next(n for n in doc["nodes"] if n.get("name") == "col_bridge_deck")["translation"] = [0.0, by, 0.0]  # (Y-up)
    js = json.dumps(doc).encode()
    js += b" " * (-len(js) % 4)
    body = struct.pack("<I4s", len(js), b"JSON") + js + rest
    return b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body


class Walker:
    """Input frames into the authority, one tick each, as a client sends them."""

    def __init__(self, room: SceneRoom) -> None:
        self.room, self.seq = room, 0

    def body(self, eid: int) -> Any:
        return self.room.players[eid].body

    def feet(self, eid: int) -> tuple[float, float]:
        box = entity_aabb(self.body(eid))
        return box.x / 32, box.y / 32

    def where(self, eid: int) -> tuple[float, str | None]:
        b = self.body(eid)
        return b.mesh_entity_data.get("elevation"), getattr(b, "mesh_hd2d_floor", None)

    def drive(self, eid: int, dx: int, dy: int, target: float, ticks: int = 400) -> bool:
        """Hold a direction until the feet reach ``target`` m on that axis (True) or stop moving (False), then let
        go: a stop, read on a tick of its own (the server reads one input a tick, M4-3)."""
        axis = 0 if dx else 1
        try:
            for _ in range(ticks):
                if (self.feet(eid)[axis] - target) * (dx or dy) >= 0:
                    return True
                self.send(eid, dx, dy)
                before = self.feet(eid)
                self.room.step()
                if self.feet(eid) == before:
                    return False
            return False
        finally:
            self.send(eid, 0, 0)
            self.room.step()

    def send(self, eid: int, dx: int, dy: int) -> None:
        self.seq += 1
        self.room.input(eid, {"v": wire.VERSION, "type": "input", "tick": 0, "entity": eid, "seq": self.seq, "dx": dx, "dy": dy})


def test_the_authority_walks_the_crossing_on_the_shared_floor_solver(crossing: dict[str, bytes]) -> None:
    room = make_room(crossing)
    assert room.world is not None and room.digest == room.world.collision_digest()
    walk = Walker(room)
    a = room.join()
    assert walk.drive(a, -1, 0, 10.0) and walk.where(a) == (0.0, "ground")
    assert walk.drive(a, 0, 1, 6.5)
    elevation, floor = walk.where(a)
    assert floor == "crossing/col_stairs_west" and 0.0 < elevation < 64.0, "half way up the stairs"
    assert walk.drive(a, 0, 1, 11.5) and walk.where(a) == (64.0, "crossing/col_platform_west")
    assert walk.drive(a, 1, 0, 16.0) and walk.where(a) == (64.0, "crossing/col_bridge_deck")
    assert not walk.drive(a, 0, 1, 13.5, 40), "the railing stops it"
    assert walk.drive(a, 0, -1, 11.5) and walk.drive(a, 1, 0, 22.0)
    assert walk.where(a) == (64.0, "crossing/col_platform_east")
    assert not walk.drive(a, 1, 0, 27.0, 60), "the platform's edge: no falling off"
    assert walk.drive(a, -1, 0, 22.0) and walk.drive(a, 0, -1, 3.0) and walk.where(a) == (0.0, "ground"), "down"
    assert room.template.get("elevation") is None, "moving a body never writes the room's template"


def test_two_bodies_at_one_place_on_two_floors(crossing: dict[str, bytes]) -> None:
    room = make_room(crossing)
    walk = Walker(room)
    deck, under = room.join(), room.join()
    for dx, dy, target in ((-1, 0, 10.0), (0, 1, 11.5), (1, 0, 16.0)):  # up the west stairs, onto the bridge
        assert walk.drive(deck, dx, dy, target)
    assert walk.drive(under, 0, 1, 12.0), "the other walks under the bridge"
    assert walk.drive(deck, 0, 1, walk.feet(under)[1])
    a, b = walk.body(deck), walk.body(under)
    assert abs(a.center_x - b.center_x) < 0.01 and abs(a.center_y - b.center_y) < room.step_px
    assert walk.where(deck) == (64.0, "crossing/col_bridge_deck") and walk.where(under) == (0.0, "ground")
    assert room.floors(b) == {0.0, 2.0}, "two floors stand at this place"
    walk.drive(deck, -1, 0, 15.0)
    walk.drive(under, -1, 0, 15.0)
    assert walk.where(deck) == (64.0, "crossing/col_bridge_deck") and walk.where(under) == (0.0, "ground")


def test_a_2d_rooms_identity_is_unchanged() -> None:
    with disposable_project(coop_files(), scaffold=False) as root:
        room = SceneRoom(root / COOP_SCENE, root)
        scene_hash, _scene = load_scene(root / COOP_SCENE)
    assert room.world is None and room.digest is None
    geometry = [[b.center_x, b.center_y, b.width, b.height] for b in room.solids_ever()] + [list(room._template_size())]
    assert room.identity == hashlib.sha256(json.dumps([scene_hash, geometry]).encode()).hexdigest(), "N6's own formula"


def test_rooms_the_authority_would_run_differently_are_refused(crossing: dict[str, bytes]) -> None:
    def pond(scene: dict[str, Any]) -> None:
        scene["entities"].append({"id": "pond", "x": 160.0, "y": 160.0, "behaviours": ["WaterSurface"],
                                  "behaviour_config": {"WaterSurface": {"preset": "pond", "walkable": False}}})

    def river(scene: dict[str, Any]) -> None:
        scene["settings"]["hd2d"]["rivers"] = [{"id": "brook", "points": [[64, 64, 48, 0], [64, 600, 48, 0]]}]

    def broken_river(scene: dict[str, Any]) -> None:  # (lenient: set aside, the room stands without it)
        scene["settings"]["hd2d"]["rivers"] = [{"id": "brook", "points": [[64, 64], [64, 600]], "width": 48}]

    def nothing_3d(scene: dict[str, Any]) -> None:
        scene["settings"]["hd2d"].pop("structures")

    def bad_block(scene: dict[str, Any]) -> None:
        scene["settings"]["hd2d"]["structures"][0]["model"] = "assets/models/missing.glb"

    def raised_template(scene: dict[str, Any]) -> None:
        scene["entities"][0]["elevation"] = 64.0  # 2 m up over open ground

    def template_in_the_hut(scene: dict[str, Any]) -> None:
        scene["entities"][0].update(x=624.0, y=432.0 + 18.0)

    broken = {**crossing, MODEL: b"not a model"}
    for files, message in ((edited(crossing, pond), "rivers or ponds"), (edited(crossing, river), "rivers or ponds"),
                           (edited(crossing, broken_river), "partly sets aside: settings.hd2d.rivers"),
                           (edited(crossing, nothing_3d), "single-player moves it in 2D"),
                           (edited(crossing, bad_block), "single-player plays 2D"),
                           (broken, "single-player plays 2D"),
                           (edited(crossing, raised_template), "can't stand where it is"),
                           (edited(crossing, template_in_the_hut), "can't stand where it is")):
        with pytest.raises(Unsupported, match=message):
            make_room(files)


# --- N7: doors and arrivals ------------------------------------------------------------------------------------------

def door(eid: str, x: float, y: float, spawn: str, size: float = 32.0) -> dict[str, Any]:
    return {"id": eid, "x": x, "y": y, "behaviours": ["SceneTransition"],
            "behaviour_config": {"SceneTransition": {"allow_interact": False, "area_height": size, "area_width": size,
                                                     "spawn_id": spawn, "target_scene": "deck",
                                                     "target_tag": "player", "trigger_on_touch": True}}}


def world_files(crossing: dict[str, bytes], doors: list[dict[str, Any]]) -> dict[str, bytes]:
    """Two crossing rooms: ``start`` (the demo's, with ``doors``) and ``deck``, whose player stands on the east
    platform 2 m up, with an arrival on the west platform (``high``) and one on the ground (``low``)."""
    def start(scene: dict[str, Any]) -> None:
        scene["entities"] += doors

    def deck(scene: dict[str, Any]) -> None:
        scene["entities"][0].update(x=707.0, y=384.0, elevation=64.0)
        scene["entities"] += [{"id": "high", "tag": "spawn_point", "spawn_id": "high", "x": 317.0, "y": 391.5},
                              {"id": "low", "tag": "spawn_point", "spawn_id": "low", "x": 512.0, "y": 114.0}]

    files = {**edited(crossing, start), DECK_SCENE: edited(crossing, deck)[SCENE]}
    files[WORLD_FILE] = json.dumps({"id": "main", "start_scene": "start", "scenes": {
        "start": {"path": SCENE}, "deck": {"path": DECK_SCENE}}}).encode()
    return files


def make_world(files: dict[str, bytes]) -> World:
    with disposable_project(files, scaffold=False) as root:
        return World(root)


def walk_through(world: World, pid: int, dx: int, dy: int, ticks: int = 60) -> None:
    for seq in range(1, ticks + 1):
        m = world.members[pid]
        world.input(pid, {"v": wire.VERSION, "type": "input", "tick": 0, "room": m.instance, "entity": m.eid, "seq": seq, "dx": dx, "dy": dy})
        world.step()
        if m.instance != world.hub.id or world.members[pid].outbox and any(
                f["type"] == "notice" for f in world.members[pid].outbox):
            return


def test_a_door_over_more_than_one_floor_height_loads(crossing: dict[str, bytes]) -> None:
    """M1-A-2 refused a door under (and on) the bridge; since M3-3 it fires for a player on its level only, in both
    runtimes (tests/test_hd2d_doors_floors.py), so it loads."""
    assert make_world(world_files(crossing, [door("ground_door", 512.0, 200.0, "high")])).defs["start"].doors
    assert make_world(world_files(crossing, [door("bridge_door", 512.0, 400.0, "high")])).defs["start"].doors


def test_an_arrival_keeps_the_rooms_elevation_and_one_that_cant_stand_is_refused(crossing: dict[str, bytes]) -> None:
    world = make_world(world_files(crossing, [door("up", 512.0, 200.0, "high"), door("down", 512.0, 60.0, "low")]))
    pid, _ = world.connect(None)
    walk_through(world, pid, 0, -1)  # into "down": the deck room's player (2 m up) can't stand on its ground arrival
    m = world.members[pid]
    assert m.instance == world.hub.id and m.eid in world.hub.room.players, "refused: still where it was"
    assert {"v": wire.VERSION, "type": "notice", "code": "transfer_failed"} in m.outbox
    assert world.history[-1][2:] == ("transfer", pid, f"{world.hub.id} down transfer_failed")
    m.outbox.clear()
    walk_through(world, pid, 0, 1)  # into "up": its arrival on the west platform
    m = world.members[pid]
    assert world.instances[m.instance or ""].key == "deck"
    body = world.instances[m.instance or ""].room.players[m.eid].body
    assert (body.center_x, body.center_y) == (317.0, 391.5), "the marker's x/y"
    assert body.mesh_entity_data["elevation"] == 64.0, "the room's player elevation, kept (single-player's rule)"
    world.input(pid, {"v": wire.VERSION, "type": "input", "tick": 0, "room": m.instance, "entity": m.eid, "seq": 999, "dx": 0, "dy": -1})
    world.step()
    assert getattr(body, "mesh_hd2d_floor", None) == "crossing/col_platform_west" and body.mesh_entity_data["elevation"] == 64.0


# --- before a client enters ------------------------------------------------------------------------------------------

def test_a_client_whose_collision_differs_is_refused_before_it_enters(crossing: dict[str, bytes]) -> None:
    server = make_room(crossing)
    same, other = make_room(dict(crossing)), make_room({**crossing, MODEL: raised_deck(crossing[MODEL])})
    assert same.identity == server.identity
    assert other.digest != server.digest and other.identity != server.identity, "only the deck's collider moved"
    check_state(server.snapshot(), same.identity)

    async def join(client: SceneRoom) -> None:
        host = Server(server)
        port = await host.start()
        try:
            async with connect(port, check=lambda m: check_state(m, client.identity)):
                pass
        finally:
            await host.close()

    asyncio.run(join(same))
    with pytest.raises(wire.Invalid, match="different scene"):  # N6: its first snapshot, in the welcome
        asyncio.run(join(other))
    files = world_files(crossing, [door("up", 512.0, 200.0, "high")])
    served = make_world(files)
    hello = welcome("0" * 32, 1, "a" * 64, served.identity)
    check_welcome(hello, make_world(dict(files)).identity)
    with pytest.raises(wire.Invalid, match="different world"):  # N7: at welcome, before any room
        check_welcome(hello, make_world({**files, MODEL: raised_deck(files[MODEL])}).identity)


def test_a_window_whose_room_fell_back_to_2d_or_differs_does_not_join(crossing: dict[str, bytes]) -> None:
    from engine.hd2d.settings import parse_hd2d
    from engine.hd2d.world import build_world
    from mesh_net.scene_room import contained

    room = make_room(crossing)
    for window, reason in ((SimpleNamespace(hd2d_world=None, hd2d_error="GlbError: no texture"), "in 2D"),
                           (SimpleNamespace(hd2d_world=room.world, hd2d_error="driver refused"), "in 2D"),
                           (SimpleNamespace(), "in 2D")):
        with pytest.raises(JoinRefused, match=reason):
            SceneView(window, None, room)  # (refused before it touches the window)
    with disposable_project({**crossing, MODEL: raised_deck(crossing[MODEL])}, scaffold=False) as root:
        scene = json.loads((root / SCENE).read_text(encoding="utf-8"))
        theirs = build_world(parse_hd2d(scene["settings"]["hd2d"]), scene["entities"], contained(root))[0]
    with pytest.raises(JoinRefused, match="differs"):
        check_window_world(SimpleNamespace(hd2d_world=theirs, hd2d_error=None), room)
    check_window_world(SimpleNamespace(hd2d_world=room.world, hd2d_error=None), room)
    with disposable_project(coop_files(), scaffold=False) as root:
        flat = SceneRoom(root / COOP_SCENE, root)
    check_window_world(SimpleNamespace(), flat)  # a 2D room needs no collision world


def decorative_pond(scene: dict[str, Any]) -> None:
    """A walkable pond (no limit to walking: the room is run) that single-player leaves out (SceneLoader's
    validate_entity: a behaviour no game has)."""
    scene["entities"].append({"id": "pond", "x": 800.0, "y": 640.0, "behaviours": ["WaterSurface", "NoSuchBehaviour"],
                              "behaviour_config": {"WaterSurface": {"preset": "pond", "walkable": True}}})


def test_the_authority_keeps_exactly_the_entities_single_player_keeps(crossing: dict[str, bytes]) -> None:
    from engine.behaviours import load_builtin_behaviours
    from engine.hd2d.settings import parse_hd2d
    from engine.hd2d.world import build_world
    from engine.scene_loader import SceneLoader
    from mesh_net.scene_room import contained

    load_builtin_behaviours()  # (as the game window has them)
    files = edited(crossing, decorative_pond)
    with disposable_project(files, scaffold=False) as root:
        room = SceneRoom(root / SCENE, root)
        scene = SceneLoader().load_scene(str(root / SCENE))  # single-player's loader
        window = build_world(parse_hd2d(scene["settings"]["hd2d"], lenient=True), scene["entities"], contained(root))[0]
    assert "pond" not in room.ids and "pond" not in [e.get("id") for e in scene["entities"]]
    assert window is not None and room.digest == window.collision_digest()
    check_window_world(SimpleNamespace(hd2d_world=window, hd2d_error=None), room)  # the client joins
    assert room.identity == make_room(edited(crossing, lambda s: None)).identity, "as if the pond weren't there"


def test_the_authoritys_copy_of_the_behaviour_metadata_is_current() -> None:
    from engine.behaviours import load_builtin_behaviours
    from engine.behaviours.registry import validation_metadata

    load_builtin_behaviours()
    copy = json.loads((REPO / "mesh_net" / "behaviours.json").read_text(encoding="utf-8"))
    assert copy == json.loads(json.dumps(validation_metadata())), "run: py -3.13 tooling/write_net_behaviours.py"


def test_a_stale_entry_in_the_copy_is_caught() -> None:
    """A behaviour removed from the code but left in mesh_net/behaviours.json (which the authority has registered in
    this process already) is not part of the registry's own metadata, so the copy no longer matches it."""
    from engine.behaviours import load_builtin_behaviours, registry

    load_builtin_behaviours()
    stale = {**json.loads((REPO / "mesh_net" / "behaviours.json").read_text(encoding="utf-8")),
             "RemovedBehaviour": {"fields": [], "params": {}}}
    registry.register_validation_metadata(stale)  # (as loading a room registers the copy)
    try:
        assert registry.get_behaviour_info("RemovedBehaviour") is not None
        assert "RemovedBehaviour" not in registry.validation_metadata()
        assert stale != json.loads(json.dumps(registry.validation_metadata())), "the drift test fails on it"
    finally:
        registry._BEHAVIOUR_INFO.pop("RemovedBehaviour", None)
        registry._NAME_ALIASES.pop("removedbehaviour", None)
        registry.BEHAVIOUR_PARAM_DEFS.pop("RemovedBehaviour", None)


def test_a_refused_room_stays_said_and_is_never_resumed_into(crossing: dict[str, bytes]) -> None:
    from mesh_net.world_client import WorldArena

    room = make_room(crossing)
    window = SimpleNamespace(scene_controller=SimpleNamespace(room_path="x"), game_state_controller=None,
                             load_scene=lambda path: None, clear=lambda color: None, hd2d_world=None,
                             hd2d_error="GlbError: a texture is missing")
    enter = {"room": "start:3"}
    arena = SimpleNamespace(notice=None, pending=enter, room="start:3", key="start", window=window, loads=[],
                            defs={"start": SimpleNamespace(path=SCENE, proto=room)}, arcade=None, note=lambda e: None,
                            refusal=None, token="t" * 64, request=None, connected=True, view=None, status="", last=None)
    WorldArena.draw(arena, 1.0)
    assert arena.view is None and arena.pending is None and arena.request == "disconnect"
    assert arena.token is None, "no resume back into the refused room"
    arena.connected, arena.status = False, "Disconnected | R resume / N new"  # (what Arena.run then says)
    WorldArena.draw(arena, 1.1)
    assert arena.status.startswith("Refused: this window plays the HD-2D room in 2D (GlbError: a texture is missing)")
    arena.connected, arena.pending = True, enter  # put back there (a retained character): refused again, said again
    WorldArena.draw(arena, 1.2)
    arena.connected = False
    WorldArena.draw(arena, 1.3)
    assert arena.view is None and arena.status.startswith("Refused:")


def test_the_authority_runs_an_hd2d_room_without_graphics(crossing: dict[str, bytes], tmp_path: Path) -> None:
    """In a fresh process: no Arcade, so no behaviours loaded (scene validation reads mesh_net/behaviours.json), and
    the same room (its dropped pond included) as this process, which has them, builds."""
    from engine.behaviours import load_builtin_behaviours

    load_builtin_behaviours()
    files = edited(crossing, decorative_pond)
    project = tmp_path / "proj"
    for rel, data in files.items():
        (project / rel).parent.mkdir(parents=True, exist_ok=True)
        (project / rel).write_bytes(data)
    code = ("import sys; from pathlib import Path; from mesh_net.scene_room import *; from mesh_net.server import Server\n"
            "from mesh_net import protocol as wire\n"
            f"files = {{p.relative_to(r).as_posix(): p.read_bytes() for r in [Path({str(project)!r})] for p in r.rglob('*') if p.is_file()}}\n"
            "with disposable_project(files, scaffold=False) as root: room = SceneRoom(root / 'packs/core_regions/scenes/start.json', root)\n"
            "Server(room); eid = room.join()\n"
            "for seq in range(1, 31): room.input(eid, wire.input_frame(eid, seq, -1, 0, room.tick + 1)); room.step()\n"
            "assert room.world is not None and room.players[eid].body.center_x < 512 - 100\n"
            "bad = [k for k in ('arcade', 'pyglet', 'engine.game', 'engine.studio', 'engine.physics_runtime') if k in sys.modules]\n"
            "assert not bad, bad\n"
            "print(room.identity)")
    done = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
    assert done.stdout.strip().splitlines()[-1] == make_room(files).identity


# --- M3-2: wire v2 carries each body's elevation and floor ----------------------------------------------------------

DECK = "crossing/col_bridge_deck"


def deck_and_under(room: SceneRoom) -> tuple[int, int]:
    """Two players at one place: one on the bridge deck (2 m up), one on the ground under it (as above)."""
    walk = Walker(room)
    deck, under = room.join(), room.join()
    for dx, dy, target in ((-1, 0, 10.0), (0, 1, 11.5), (1, 0, 16.0)):
        assert walk.drive(deck, dx, dy, target)
    assert walk.drive(under, 0, 1, 12.0) and walk.drive(deck, 0, 1, walk.feet(under)[1])
    assert walk.where(deck) == (64.0, DECK) and walk.where(under) == (0.0, "ground")
    return deck, under


def headless_view(room: SceneRoom) -> SceneView:
    """A client's SceneView of ``room`` without a window: what SceneView.sync and draw use of one (avatars are plain
    objects; nothing is drawn)."""
    entities = SimpleNamespace(enqueue_spawn=lambda sprite, **kw: None, enqueue_despawn=lambda sprite: None,
                               apply_pending_ops=lambda scene: None)
    scene = SimpleNamespace(entities=entities, _rebuild_behaviours_for_sprite=lambda sprite: None, update=lambda dt: None,
                            _create_sprite=lambda data: SimpleNamespace(mesh_entity_data=data, mesh_behaviours=[]))
    view = SceneView.__new__(SceneView)
    view.window, view.arcade, view.scene = SimpleNamespace(hd2d_renderer=None, on_draw=lambda: None), None, scene
    view.room, view.identity, view.template = room, room.identity, dict(room.template)
    view.sprites, view.doors, view.levers, view.colors, view.avatars, view.drops = {}, [], [], {}, {}, {}
    view.enemy_colors, view.flashes, view.marks, view.textures = {}, {}, [], {}
    view.arcade = SimpleNamespace(Texture=lambda image, hash: SimpleNamespace(image=image, hash=hash),  # (marks)
                                  Sprite=lambda texture: SimpleNamespace(texture=texture, angle=0.0))
    return view


def row(state: dict[str, Any], eid: int) -> list[Any]:
    return next(r for r in state["players"] if r[0] == eid)


def test_a_body_on_the_deck_arrives_at_other_clients_at_deck_height(crossing: dict[str, bytes]) -> None:
    """The authority walks one body onto the bridge deck and another under it; a client (its room from its own files)
    receives both rows with their elevation and floor and places each avatar there: what the HD-2D renderer draws."""
    from engine.hd2d.renderer import Hd2dRenderer
    from mesh_net.playback import Playback
    from mesh_net.scene_client import SceneArena

    server = make_room(crossing)
    deck, under = deck_and_under(server)
    client = make_room(dict(crossing))
    playback = Playback(lambda s: check_state(s, client.identity, client))
    for t in range(4):  # (still: the bodies stand)
        server.step()
        state = server.snapshot()
        assert playback.push(state, t / wire.HZ)
    assert row(state, deck)[4:6] == [64.0, DECK] and row(state, under)[4:6] == [0.0, "ground"]
    view = headless_view(client)
    arena: Any = SimpleNamespace(client=SimpleNamespace(state=state, entity=under), playback=playback, view=view,
                                 last=None, prediction=Prediction())
    arena.prediction.start(client, state, under)  # (as its welcome did: its own avatar predicted from its row)
    SceneArena.draw(arena, 1.0)  # (this client is the one under the bridge; its peer is on the deck)
    peer, own = view.avatars[deck], view.avatars[under]
    assert (peer.mesh_entity_data["elevation"], peer.mesh_hd2d_floor) == (64.0, DECK)
    assert (own.mesh_entity_data["elevation"], own.mesh_hd2d_floor) == (0.0, "ground")
    assert Hd2dRenderer.elevation_of(peer) == 64.0 and Hd2dRenderer.elevation_of(own) == 0.0
    assert abs(peer.center_x - own.center_x) < 0.01, "one place, two floors"
    assert view.template.get("elevation") is None, "placing avatars never writes the room's template"


def test_the_level_on_the_wire_is_the_authoritys_own(crossing: dict[str, bytes]) -> None:
    """Up the stairs, every snapshot's row says the body's elevation and floor as the authority holds them, and each
    passes the client's own world's check; a body just joined has its floor too."""
    room, client = make_room(crossing), make_room(dict(crossing))
    walk = Walker(room)
    a = room.join()
    assert row(room.snapshot(), a)[4:6] == [0.0, "ground"], "a body not yet moved"
    walk.drive(a, -1, 0, 10.0)
    floors = set()
    for _ in range(80):
        walk.send(a, 0, 1)
        room.step()
        state = room.snapshot()
        check_state(state, client.identity, client)
        elevation, floor = walk.where(a)
        assert row(state, a)[4:6] == [elevation, floor]
        floors.add(floor)
    assert {"ground", "crossing/col_stairs_west", "crossing/col_platform_west"} <= floors


def test_malformed_rows_are_refused_whole(crossing: dict[str, bytes]) -> None:
    """Wrong arity or types, NaN or infinity, an elevation past the bound, a floor id the room doesn't have: refused
    (wire.Invalid, the connection's end), before anything is applied."""
    from mesh_net.demo import reason
    from mesh_net.world_client import WorldArena

    room = make_room(crossing)
    deck, _under = deck_and_under(room)
    room.step()
    good = room.snapshot()
    check_state(good, room.identity, room)
    d = row(good, deck)

    def with_deck(new: list[Any]) -> dict[str, Any]:
        return {**good, "players": [new if r[0] == deck else r for r in good["players"]]}

    nan = [*d[:4], float("nan"), DECK, *d[6:]]
    bad_rows = [d[:5], d[:6], [*d, None], [*d[:4], "64", DECK, *d[6:]], [*d[:4], True, DECK, *d[6:]],
                [*d[:4], None, DECK, *d[6:]], nan, [*d[:4], float("inf"), DECK, *d[6:]],
                [*d[:4], -float("inf"), DECK, *d[6:]], [*d[:4], 100_001.0, DECK, *d[6:]], [*d[:4], 64.0, 3, *d[6:]],
                [*d[:4], 64.0, "", *d[6:]], [*d[:4], 64.0, "x" * 129, *d[6:]],
                [*d[:4], 64.0, "crossing/col_no_such", *d[6:]],
                [d[0], float("nan"), *d[2:]]]
    for bad in bad_rows:
        with pytest.raises(wire.Invalid):
            check_state(with_deck(bad), room.identity, room)
    # The world client: a refused frame changes nothing it holds (no half-applied state).
    arena: Any = SimpleNamespace(identities={"start": room.identity}, defs={"start": SimpleNamespace(proto=room)},
                                 room=None, key=None, entity=None, state=None, playback=None, pending=None, phase="loading",
                                 feedback=Feedback(), prediction=Prediction(), seq=0, actions=[], view=None, shown=None)
    enter = {"v": wire.VERSION, "type": "enter", "room": "start:1", "key": "start", "entity": deck}
    with pytest.raises(wire.Invalid):
        WorldArena.on_frame(arena, {**enter, "state": with_deck(nan)}, 0.0)
    assert (arena.room, arena.state, arena.playback, arena.pending) == (None, None, None, None)
    WorldArena.on_frame(arena, {**enter, "state": good}, 0.0)
    kept = arena.state
    newer = {**with_deck([*d[:4], float("inf"), DECK, *d[6:]]), "tick": good["tick"] + 1}
    with pytest.raises(wire.Invalid):
        WorldArena.on_frame(arena, {"v": wire.VERSION, "type": "room_state", "room": "start:1", "state": newer}, 0.1)
    assert arena.state is kept and arena.playback.states[-1] is kept
    # Inconsistent (well-formed, newer, but the deck body standing on the ground at deck height): refused whole too.
    wrong = {**with_deck([*d[:4], 64.0, "ground", *d[6:]]), "tick": good["tick"] + 1}
    with pytest.raises(wire.Invalid, match="is not under it") as refused:
        WorldArena.on_frame(arena, {"v": wire.VERSION, "type": "room_state", "room": "start:1", "state": wrong}, 0.1)
    assert arena.state is kept and list(arena.playback.states) == [kept], "nothing of it applied"
    assert "is not under it" in reason(refused.value), "the session ends saying why"


def test_rows_inconsistent_with_the_clients_own_world_are_refused(crossing: dict[str, bytes]) -> None:
    """A floor that is not under the row at its elevation (the deck's id at ground height, the ground at deck height,
    a floor elsewhere in the room) is refused, never corrected."""
    room = make_room(crossing)
    deck, under = deck_and_under(room)
    room.step()
    good = room.snapshot()
    d, u = row(good, deck), row(good, under)
    for bad_deck, bad_under in (([*d[:4], 0.0, DECK, *d[6:]], u), (d, [*u[:4], 0.0, DECK, *u[6:]]),
                                ([*d[:4], 64.0, "ground", *d[6:]], u),
                                ([*d[:4], 64.0, "crossing/col_platform_east", *d[6:]], u),
                                ([*d[:4], 50.0, DECK, *d[6:]], u)):
        with pytest.raises(wire.Invalid, match="is not under it"):
            check_state({**good, "players": sorted([bad_deck, bad_under])}, room.identity, room)
    check_state({**good, "players": sorted([[*d[:4], 60.0, DECK, *d[6:]], u])}, room.identity, room)  # (within a step)


def test_a_client_can_never_place_a_body(crossing: dict[str, bytes]) -> None:
    """Input frames are a direction and an action only: one carrying an elevation, a floor or a position is refused
    (N6 and N7), over the socket the session ends, and the body stays where the server had it."""
    from engine.hd2d.world import elevation_of

    room = make_room(crossing)
    eid = room.join()
    base = {"v": wire.VERSION, "type": "input", "tick": 0, "entity": eid, "seq": 1, "dx": 0, "dy": 0}
    for extra in ({"elevation": 64.0}, {"floor": DECK}, {"x": 1.0, "y": 1.0}, {"z": 2.0}, {"level": [64.0, DECK]}):
        with pytest.raises(wire.Invalid):
            room.input(eid, {**base, **extra})
    body = room.players[eid].body
    assert (elevation_of(body), body.mesh_hd2d_floor) == (0.0, "ground")
    world = make_world(world_files(crossing, [door("up", 512.0, 200.0, "high")]))
    pid, _ = world.connect(None)
    m = world.members[pid]
    with pytest.raises(wire.Invalid):
        world.input(pid, {**base, "room": m.instance, "entity": m.eid, "elevation": 64.0, "floor": DECK})

    async def run() -> None:
        server = Server(make_room(crossing))
        port = await server.start()
        try:
            async with connect(port, check=lambda s: check_state(s, room.identity, room)) as client:
                client.writer.write(wire.encode({**base, "entity": client.entity, "elevation": 64.0, "floor": DECK}))
                with pytest.raises((EOFError, ConnectionError, wire.Invalid)):
                    for _ in range(200):
                        await client.receive()
            assert not server.room.players and len(server.offline) == 1
            [(_expiry, kept)] = server.offline.values()
            assert isinstance(kept, Player)
            assert (elevation_of(kept.body), kept.body.mesh_hd2d_floor) == (0.0, "ground"), "never the client's"
        finally:
            await server.close()

    asyncio.run(run())


def test_a_row_within_its_rounding_of_a_floors_edge_is_accepted(crossing: dict[str, bytes]) -> None:
    """x/y travel rounded to 0.01 px: a body just inside the deck's edge can arrive just outside it. Within the
    rounding (0.005 px) the row stands on the deck; beyond it, it does not."""
    from engine.hd2d.settings import PIXELS_PER_METRE

    room = make_room(crossing)
    deck, _under = deck_and_under(room)
    room.step()
    good = room.snapshot()
    d = row(good, deck)
    assert room.world is not None
    box = entity_aabb(room.players[deck].body)
    offset = box.x - room.players[deck].body.center_x  # (the feet box's centre from the body's)
    y = box.y / PIXELS_PER_METRE

    def on_deck(x: float) -> bool:
        assert room.world is not None
        return any(s.floor == DECK for _h, s in room.world.heights_at(x, y))

    inside, outside = box.x / PIXELS_PER_METRE, box.x / PIXELS_PER_METRE
    while on_deck(outside):  # east along the deck to past its edge
        outside += 0.25
    for _ in range(60):  # then the edge, to well under a millionth of a pixel
        middle = (inside + outside) / 2
        inside, outside = (middle, outside) if on_deck(middle) else (inside, middle)

    def at(past_px: float) -> dict[str, Any]:
        """The deck row with its feet ``past_px`` beyond the deck's edge."""
        x = outside * PIXELS_PER_METRE + past_px - offset
        return {**good, "players": [[*r[:1], x, *r[2:]] if r[0] == deck else r for r in good["players"]]}

    assert not on_deck(outside + 0.004 / PIXELS_PER_METRE), "the row's own point is off the deck"
    check_state(at(0.004), room.identity, room)  # within the rounding: accepted
    for past in (0.009, 0.02):  # beyond it: refused (0.009: a tolerance of 0.01 px or more would take it)
        with pytest.raises(wire.Invalid, match="is not under it"):
            check_state(at(past), room.identity, room)
    assert d[4:6] == [64.0, DECK]
