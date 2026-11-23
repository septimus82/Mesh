"""HD-2D online M3-5/M3-6: two clients share one HD-2D room. The scene, the two-window run, and its rendered evidence.

    py -3.13 tooling/m3_two_client_evidence.py OUT    build the room, play the run, save the frames to OUT/frames
                                                       (and facts.json); the run's facts are checked with the
                                                       acceptance test's own assertions before anything is kept

The room is M1-B's Crossing (tooling/hd2d_m1b_scene.py, built in Mesh Studio with its own input events), then given,
through the documented authoring operations (``mesh author apply``: the same validated operations Studio and the MCP
server use, engine/project_ops.py), three things on the ground directly under the bridge deck:

- a bandit: Studio's Person, renamed, tagged ``enemy``, with Health (1 HP) and a DropTable (its loot: the item);
- a walk-in door (an invisible Passage, 0.75 x 1 m) linked to the starter's Start room, with its door back.

The run (``run``) is the acceptance's scenario. A real authority (mesh_net.server.WorldServer, in this process) and two
real hidden client windows (tooling/net_world_probe.py, each its own process with its own copy of the project) play it,
driven only through the probes' command channel with key presses; every window fact is read from the window's own
objects. Two more windows try to join and are refused: one whose bridge deck collider is 0.5 m higher, one whose room
fell back to 2D. ``run`` records what it saw (the test, tests/test_mesh_net_hd2d_gpu.py, asserts on it) and, given a
``shoot`` folder, saves both windows' read-back framebuffers at the key moments and a frame sequence of B passing under
A. The gpu lane runs it without ``shoot``: nothing is written into the repository by the test.

Hidden windows only, audio at master 0 (the Crossing's build sets it), no OS input.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))  # (tests.net_walk, the window tests' command channel, the acceptance's checks)
CROSSING, START = "crossing", "start"
PX = 32.0
# Under the bridge deck (x 13-19 m, standable y 19.5-20.5 m) on the ground, in the underpass (x 14.5-17.5 m):
BANDIT = (544.0, 672.0)  # 17 m, 21 m: its picture's centre (its feet 18 px south, 20.44 m: under the deck)
DOOR = (480.0, 656.0)  # 15 m, 20.5 m
DOOR_AREA = (24, 32)  # px: an invisible Passage, clear of a player at x 16 m (its picture spans 15.5-16.5 m)
START_DOOR = (640.0, 320.0)  # the Start room's door back (a 2D room, 768 x 512 px)
LOOT = [{"gold": 5}]


def _author(project: Path, changes: list[dict[str, Any]], scratch: Path) -> dict[str, Any]:
    """``mesh author apply`` (the documented authoring operations) on the project's files: all or nothing."""
    path = scratch / "changes.json"
    path.write_text(json.dumps(changes), encoding="utf-8")
    done = subprocess.run([sys.executable, "-m", "mesh_cli", "author", "apply", str(path), "--project", str(project)],
                          cwd=REPO, capture_output=True, text=True, timeout=300)
    path.unlink()
    assert done.returncode == 0, done.stdout + done.stderr
    result: dict[str, Any] = json.loads(done.stdout)
    return result


def build_scene(out: Path) -> Path:
    """M1-B's Crossing (built in Studio), with the bandit and the door under the deck: OUT/game."""
    sys.path.insert(0, str(REPO / "tooling"))
    try:
        import hd2d_m1b_scene
    finally:
        sys.path.remove(str(REPO / "tooling"))
    hd2d_m1b_scene.build(out, pictures=False)
    project = out / "game"
    made = _author(project, [
        {"op": "place_prefab", "room": CROSSING, "prefab": "person", "x": BANDIT[0], "y": BANDIT[1]},
        {"op": "rename_entity", "room": CROSSING, "entity_id": "@0", "name": "Bandit"},
        {"op": "set_entity_fields", "room": CROSSING, "entity_id": "@0", "fields": {"tag": "enemy"}},
        {"op": "remove_behaviour", "room": CROSSING, "entity_id": "@0", "behaviour": "Dialogue"},
        {"op": "add_behaviour", "room": CROSSING, "entity_id": "@0", "behaviour": "Health"},
        {"op": "set_behaviour_param", "room": CROSSING, "entity_id": "@0", "behaviour": "Health", "param": "max_hp",
         "value": 1},
        {"op": "add_behaviour", "room": CROSSING, "entity_id": "@0", "behaviour": "DropTable"},
        {"op": "set_behaviour_param", "room": CROSSING, "entity_id": "@0", "behaviour": "DropTable", "param": "drops",
         "value": LOOT},
        {"op": "link_rooms", "key_a": CROSSING, "at_a": list(DOOR), "key_b": START, "at_b": list(START_DOOR)},
    ], out)
    doors = {}
    for key in (CROSSING, START):
        scene = json.loads((project / f"packs/core_regions/scenes/{key}.json").read_text(encoding="utf-8"))
        doors[key] = next(e["id"] for e in scene["entities"] if e.get("tag") == "door"
                          and (e.get("behaviour_config") or {}).get("SceneTransition", {}).get("target_scene")
                          == (START if key == CROSSING else CROSSING))
    _author(project, [  # both made walk-in Passages (an area, the picture hidden), as the authority runs doors
        {"op": "set_door", "room": CROSSING, "entity_id": doors[CROSSING], "style": "passage",
         "width": DOOR_AREA[0], "height": DOOR_AREA[1]},
        {"op": "set_door", "room": START, "entity_id": doors[START], "style": "passage"},
    ], out)
    (out / "authored.json").write_text(json.dumps({"made": made, "doors": doors}, indent=1), encoding="utf-8")
    return project


def project_files(project: Path) -> dict[str, bytes]:
    """The project as files (its .mesh folder of caches and records left out): what each client and the server own."""
    return {p.relative_to(project).as_posix(): p.read_bytes() for p in project.rglob("*")
            if p.is_file() and ".mesh" not in p.relative_to(project).parts}


def raised_collider(glb: bytes, node: str, by: float = 0.5) -> bytes:
    """A GLB with one collider node ``by`` m higher (the art unchanged): tests/test_mesh_net_hd2d.py's raised_deck."""
    length = struct.unpack("<I", glb[12:16])[0]
    doc = json.loads(glb[20:20 + length])
    rest = glb[20 + length:]
    target = next(n for n in doc["nodes"] if n.get("name") == node)
    x, y, z = target.get("translation") or [0.0, 0.0, 0.0]
    target["translation"] = [x, y + by, z]  # (Y-up)
    js = json.dumps(doc).encode()
    js += b" " * (-len(js) % 4)
    body = struct.pack("<I4s", len(js), b"JSON") + js + rest
    return b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body


# ------------------------------------------------------------------------------------------------------------ the run
# Where the run walks (picture centres, px; the avatar's feet are 18 px below): from the start (16, 4.5 m) left to the
# west stairs, up them onto the west plateau (2 m), right along it onto the deck; back the same way down. At 2 m the
# deck stands centres y 636-680 and the plateau up to 722, its north edge a 2 m drop: PLATEAU_Y keeps 74 px (10 ticks of
# a late release) short of it.
STAIRS_X, PLATEAU_Y, GROUND_Y = 347.0, 648.0, 144.0
DECK_X = 512.0  # on the deck, its hitbox (32 px ahead) on the bandit beneath, clear of the door's area
OVER_X = 528.0  # on the deck over the underpass, where B passes beneath
SOUTH_Y, NORTH_Y = 500.0, 760.0  # B's pass: south of the plateaus (y 18 m) to north of them (22 m)
STRIKE = (544.0, 624.0)  # B on the ground below the bandit, facing up: its hitbox on the bandit, the loot in reach
DECK_Z, DECK_FLOOR = 64.0, "bridge_6m/col_deck"
BRIDGE_GLB, DECK_NODE = "assets/models/bridge_6m.glb", "col_deck"


class _Phase:
    """A part of the run: what it saw goes in ``facts[name]``; an exception ends only that part (kept as ``error``),
    so each acceptance test reads its own part, and a broken rule fails that test rather than the whole module."""

    def __init__(self, facts: dict[str, Any], name: str) -> None:
        self.facts, self.name = facts, name

    def __enter__(self) -> dict[str, Any]:
        self.facts[self.name] = {}
        part: dict[str, Any] = self.facts[self.name]
        return part

    def __exit__(self, kind: Any, exc: BaseException | None, tb: Any) -> bool:
        if isinstance(exc, Exception):
            self.facts[self.name]["error"] = f"{type(exc).__name__}: {exc}"
            return True
        return False


async def _scenario(world: Any, project: Path, raised: Path, shoot: Path | None) -> dict[str, Any]:
    from engine.physics_model import Aabb, entity_shape, shapes_overlap
    from mesh_net.server import WorldServer
    from tests.net_walk import walk
    from tests.test_mesh_net_gpu import command, stop_workers

    facts: dict[str, Any] = {}
    server = WorldServer(world)
    port = await server.start()
    procs: list[Any] = []
    names: dict[Any, str] = {}
    frames: list[str] = []
    walks: list[Any] = facts.setdefault("walks", [])  # each walk's legs and late-release carries (tests/net_walk.py)

    async def window(*extra: str) -> Any:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "tooling.net_world_probe", str(port), *extra, cwd=REPO,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        procs.append(proc)
        return proc

    async def settle(proc: Any, predicate: Any, timeout: float = 10, phases: set[str] | None = None) -> dict[str, Any]:
        """The first reply that meets ``predicate``, or the last one when ``timeout`` s pass (the test then fails on
        what it says): never raises, so what was seen is kept. ``phases``: gets every phase a reply had."""
        reply: dict[str, Any] = {}
        try:
            async with asyncio.timeout(timeout):
                while True:
                    reply = await command(proc, "state")
                    if phases is not None:
                        phases.add(reply["phase"])
                    if predicate(reply):
                        return reply
                    await asyncio.sleep(0.025)
        except TimeoutError:
            return reply

    def player(pid: int) -> Any:
        m = world.members[pid]
        return world.instances[m.instance].room.players[m.eid]

    def server_level(pid: int) -> list[Any]:
        """[x, y, elevation px, floor, room instance]: the authority's own account of the player."""
        p = player(pid)
        return [round(p.body.center_x, 2), round(p.body.center_y, 2), p.body.mesh_entity_data.get("elevation"),
                p.body.mesh_hd2d_floor, world.members[pid].instance]

    async def go(proc: Any, pid: int, key: str, target: float, within: float = 8.0) -> None:
        async def where() -> tuple[int, float, float]:
            m = world.members[pid]
            room = world.instances[m.instance].room
            body = room.players[m.eid].body
            return room.tick, body.center_x, body.center_y
        await walk(lambda cmd: command(proc, cmd), key, target, within, where, record=walks)

    async def rest(*pids: int) -> None:
        """Until each player has stood still for 8 server ticks (the movement lease, the windows' interpolation)."""
        async with asyncio.timeout(10):
            seen = {pid: (tuple(server_level(pid)), world.tick) for pid in pids}
            while True:
                await asyncio.sleep(0.01)
                for pid in pids:
                    if (now := tuple(server_level(pid))) != seen[pid][0]:
                        seen[pid] = (now, world.tick)
                if all(world.tick - since >= 8 for _, since in seen.values()):
                    return

    async def face(proc: Any, pid: int, key: str, facing: int) -> None:
        """Turn to ``facing`` (0 right, 1 up, 2 left, 3 down): ``key`` held until the server says so."""
        if player(pid).facing != facing:
            await command(proc, f"press {key}")
            try:
                async with asyncio.timeout(10):
                    while player(pid).facing != facing:
                        await asyncio.sleep(0.005)
            finally:
                await command(proc, f"release {key}")
        await rest(pid)

    async def acted(proc: Any, pid: int, key: str) -> None:
        """Tap an action key; wait until the server has run the input frame that carried it (the window's input
        sequence after the tap: tooling/net_world_probe ``seq``), and one tick more."""
        await command(proc, f"press {key}")
        sent = (await command(proc, f"release {key}"))["seq"]
        async with asyncio.timeout(10):
            while player(pid).seq <= sent:
                await asyncio.sleep(0.005)
            tick = world.tick
            while world.tick <= tick + 1:
                await asyncio.sleep(0.005)

    def view(reply: dict[str, Any], eid: int) -> list[Any] | None:
        """The avatar ``eid`` as the window holds it: [x, y, elevation px, floor] (net_world_probe.window_facts)."""
        avatars: dict[str, Any] = (reply.get("window") or {}).get("avatars") or {}
        return avatars.get(str(eid))

    def at(reply: dict[str, Any], eid: int, z: float, floor: str) -> bool:
        seen = view(reply, eid)
        return seen is not None and seen[2] == z and seen[3] == floor

    async def snap(label: str) -> None:
        """With ``shoot``: each window's picture now, read back from its framebuffer, as ``label``-a/b.png."""
        if shoot is None:
            return
        for proc in (a, b):
            path = shoot / f"{label}-{names[proc]}.png"
            await command(proc, f"frame {path}")
            frames.append(path.name)

    async def camera(proc: Any, eid: int) -> dict[str, Any]:
        """The window's camera once it has caught up with ``eid``'s avatar (its target within 0.05 m of the height
        it keeps over that avatar's feet), or as it is after 5 s: which avatar it follows, and where."""
        def caught(r: dict[str, Any]) -> bool:
            w, own = r.get("window") or {}, view(r, eid)
            return bool(own and w.get("camera") and abs(w["camera"][2] - (own[2] / PX + w["camera_height"])) < 0.05)
        r = await settle(proc, caught, 5)
        w = r.get("window") or {}
        return {"camera_target": w.get("camera_target"), "followed": w.get("followed"), "camera": w.get("camera"),
                "camera_height": w.get("camera_height"), "own": view(r, eid)}

    room_def = world.defs[CROSSING]
    bandit = next(iter(room_def.proto.enemies))
    door = next(d for d in room_def.doors if d.target == START)
    try:
        a, b = await window("--project", str(project)), await window("--project", str(project))
        names.update({a: "a", b: "b"})
        ra, rb = [await settle(p, lambda r: r["phase"] == "playing" and r["state"] is not None
                               and len(r["state"]["players"]) == 2, 90) for p in (a, b)]
        aid, bid, pa, pb = ra["entity"], rb["entity"], ra["player"], rb["player"]
        facts["join"] = {"keys": [ra["key"], rb["key"]], "identity": [ra["identity"], rb["identity"], world.identity],
                         "hd2d": [(r.get("window") or {}).get("hd2d") for r in (ra, rb)],
                         "entities": [aid, bid], "players": [pa, pb], "bandit": bandit, "door": door.id}

        # (a) each walks up the stairs onto the deck and back down while the other stands still; both windows and
        # the server say where.
        with _Phase(facts, "a") as part:
            await rest(pa, pb)
            await snap("01_start")
            for name, mover, mid, eid, other, opid in (("a", a, pa, aid, b, pb), ("b", b, pb, bid, a, pa)):
                still = server_level(opid)
                await go(mover, mid, "LEFT", STAIRS_X)
                await go(mover, mid, "UP", PLATEAU_Y)
                await go(mover, mid, "RIGHT", DECK_X)
                await rest(mid)
                up = {"server": server_level(mid), "own": view(await command(mover, "state"), eid),
                      "peer": view(await settle(other, lambda r, e=eid: at(r, e, DECK_Z, DECK_FLOOR)), eid)}
                await snap(f"02_{name}_on_deck")
                await go(mover, mid, "LEFT", STAIRS_X)
                await go(mover, mid, "DOWN", GROUND_Y)
                await rest(mid)
                down = {"server": server_level(mid), "own": view(await command(mover, "state"), eid),
                        "peer": view(await settle(other, lambda r, e=eid: at(r, e, 0.0, "ground")), eid)}
                part[name] = {"up": up, "down": down, "other_before": still, "other_after": server_level(opid)}

        # (b) A on the deck over the underpass; B walks beneath it from south of the deck to north of it, then stands
        # directly under A.
        with _Phase(facts, "b") as part:
            await go(a, pa, "LEFT", STAIRS_X)
            await go(a, pa, "UP", PLATEAU_Y)
            await go(a, pa, "RIGHT", OVER_X)
            await go(b, pb, "RIGHT", OVER_X)
            await go(b, pb, "UP", SOUTH_Y)
            await rest(pa, pb)
            part["above"] = server_level(pa)
            samples: list[dict[str, Any]] = []
            shot_at = -100.0
            await command(b, "press UP")
            try:
                async with asyncio.timeout(20):
                    while (here := server_level(pb))[1] < NORTH_Y - 16:
                        samples.append({"a": server_level(pa), "b": here})
                        if shoot is not None and here[1] - shot_at >= 20:  # (a frame each 20 px B walks)
                            shot_at = here[1]
                            await snap(f"seq_{sum(1 for f in frames if f.startswith('seq')) // 2:02d}")
                        await asyncio.sleep(0.01)
            finally:
                await command(b, "release UP")
            part["samples"] = samples
            await go(b, pb, "UP", NORTH_Y, 16)
            part["passed"] = server_level(pb)
            await go(b, pb, "DOWN", part["above"][1], 4)
            await rest(pa, pb)
            part["a"], part["b"] = server_level(pa), server_level(pb)
            ra, rb = await command(a, "state"), await command(b, "state")
            part["windows"] = {"a": {"own": view(ra, aid), "peer": view(ra, bid)},
                               "b": {"own": view(rb, bid), "peer": view(rb, aid)}}
            part["look"] = {"a": (await command(a, "look")).get("look"), "b": (await command(b, "look")).get("look")}
            await snap("03_a_over_b_under")

        # (d) there, each window's camera follows its own avatar, at that avatar's height.
        with _Phase(facts, "d") as part:
            part["a"], part["b"] = await camera(a, aid), await camera(b, bid)
            part["entities"] = {"a": aid, "b": bid}

        # (c) from the deck A strikes at the bandit beneath, then reaches for its loot (each in planar reach: only the
        # floors between them can refuse it); B on the ground does each.
        with _Phase(facts, "c") as part:
            await go(a, pa, "LEFT", DECK_X, 4)
            await face(a, pa, "RIGHT", 0)
            p = player(pa)
            enemy = world.instances[world.members[pa].instance].room.enemies[bandit]
            hit = Aabb(p.body.center_x + 32.0, p.body.center_y, 32.0, 32.0)  # (SceneRoom._attack's, facing right)
            part["a_at"], part["a_facing"] = server_level(pa), p.facing
            part["a_planar_hit"] = shapes_overlap(hit, entity_shape(enemy.body))
            part["hp_before"] = enemy.state.hp
            await acted(a, pa, "SPACE")
            part["after_a_attack"] = {"hp": enemy.state.hp, "dead": enemy.state.dead}
            await go(b, pb, "RIGHT", STRIKE[0], 4)
            await go(b, pb, "DOWN", STRIKE[1])
            await face(b, pb, "UP", 1)
            await snap("04_a_struck_from_deck")
            await acted(b, pb, "SPACE")
            part["after_b_attack"] = {"hp": enemy.state.hp, "dead": enemy.state.dead, "dropped": enemy.dropped}
            seen = [await settle(w, lambda r: bool(r["state"] and bandit in r["state"]["drops"])) for w in (a, b)]
            part["drops_seen"] = [r["state"]["drops"] if r.get("state") else None for r in seen]
            part["a_loot_distance"] = round(((p.body.center_x - enemy.body.center_x) ** 2
                                             + (p.body.center_y - enemy.body.center_y) ** 2) ** 0.5, 2)
            await acted(a, pa, "E")
            part["after_a_take"] = {"dropped": enemy.dropped, "held": enemy.holder is not None}
            await snap("05_a_reached_for_loot")
            await acted(b, pb, "E")
            room = world.instances[world.members[pb].instance].room
            part["after_b_take"] = {"dropped": enemy.dropped, "b": world.members[pb].eid,
                                    "holder": next((e for e, pl in room.players.items() if pl is enemy.holder), None)}
            seen = [await settle(w, lambda r: bool(r["state"] and r["state"]["loot"])) for w in (a, b)]
            part["loot_seen"] = [r["state"]["loot"] if r.get("state") else None for r in seen]
            await snap("06_b_took_loot")

        # (e) two more windows try to join: one whose bridge deck collider is 0.5 m higher (its own files make
        # another world: refused at welcome, before any room), one whose room falls back to 2D (it refuses the
        # room). The two players play on.
        async def windows_now() -> dict[str, Any]:
            """Each player's window, once it shows two players (or as it is after 10 s): [phase, entity, players]."""
            seen = [await settle(w, lambda r: r["state"] is not None and len(r["state"]["players"]) == 2) for w in (a, b)]
            return {name: [r.get("phase"), r.get("entity"), sorted(x[0] for x in (r.get("state") or {}).get("players", []))]
                    for name, r in zip("ab", seen)}

        with _Phase(facts, "e") as part:
            part["before"] = {"a": server_level(pa), "b": server_level(pb),
                              "online": sorted(i for i, m in world.members.items() if m.online)}
            other = await window("--project", str(raised))
            phases: set[str] = set()
            got = await settle(other, lambda r: r["phase"] == "disconnected", 60, phases)
            part["raised"] = {k: got.get(k) for k in ("phase", "status", "loads", "player", "refusal")}
            part["raised"]["phases"] = sorted(phases)
            part["after_raised"] = {"a": server_level(pa), "b": server_level(pb),
                                    "online": sorted(i for i, m in world.members.items() if m.online)}
            part["windows_after_raised"] = await windows_now()
            flat = await window("--project", str(project), "--fail-hd2d")
            phases = set()
            got = await settle(flat, lambda r: r["phase"] == "disconnected" and bool(r.get("refusal")), 60, phases)
            part["flat"] = {k: got.get(k) for k in ("phase", "status", "loads", "player", "refusal", "hd2d_error")}
            part["flat"]["phases"] = sorted(phases)
            member = world.members.get(got.get("player"))
            part["flat_member"] = {"online": member.online, "eid": member.eid} if member else None
            tick = world.tick
            async with asyncio.timeout(10):
                while world.tick < tick + 10:  # (the server runs on)
                    await asyncio.sleep(0.01)
            part["server_ticks"] = world.tick - tick
            part["after"] = {"a": server_level(pa), "b": server_level(pb),
                             "online": sorted(i for i, m in world.members.items() if m.online)}
            part["windows"] = await windows_now()
            part["workers"] = await stop_workers([other, flat])
            procs.remove(other)
            procs.remove(flat)

        # (c, last: it moves B) A walks over the door beneath on the deck, in planar contact with its area: no
        # transfer. B walks into it on the ground: through to Start.
        with _Phase(facts, "door") as part:
            await go(b, pb, "DOWN", SOUTH_Y)  # (B out of A's way, south of the deck)
            touched = False
            await command(a, "press LEFT")
            try:
                async with asyncio.timeout(20):
                    while world.members[pa].instance.startswith(CROSSING) and player(pa).body.center_x > door.x - 16:
                        body = player(pa).body
                        hw, hh = body.width / 2, body.height / 2  # (Door.touches' area test, without the floors)
                        touched = touched or (body.center_x - hw < door.x + door.half_w
                                              and body.center_x + hw > door.x - door.half_w
                                              and body.center_y - hh < door.y + door.half_h
                                              and body.center_y + hh > door.y - door.half_h)
                        await asyncio.sleep(0.005)
            finally:
                await command(a, "release LEFT")
            await rest(pa)
            part["a_touched_area"], part["a_after"] = touched, server_level(pa)
            ra = await settle(a, lambda r: r["key"] == CROSSING and r["shown"] == r["room"])
            part["a_window"] = {"key": ra.get("key"), "loads": ra.get("loads")}
            await snap("07_a_over_door")
            await go(b, pb, "LEFT", door.x, 4)
            await command(b, "press UP")
            try:
                rb = await settle(b, lambda r: r["key"] == START and r["phase"] == "playing" and r["shown"] == r["room"])
            finally:
                await command(b, "release UP")
            part["b_window"] = {"key": rb.get("key"), "loads": rb.get("loads")}
            part["b_after"] = server_level(pb)
            ra = await settle(a, lambda r: r["state"] is not None and [x[0] for x in r["state"]["players"]] == [aid])
            part["a_sees"] = [x[0] for x in ra["state"]["players"]] if ra.get("state") else None
            await snap("08_b_through_door")
        facts["foreign_keys"] = {n: (await command(w, "state"))["foreign_keys"] for n, w in (("a", a), ("b", b))}
        facts["frames"] = frames
        facts["history"] = [list(h) for h in world.history]
        facts["transfers"] = [[h[3], h[4]] for h in world.history if h[2] == "transfer"]  # (player id, what happened)
    finally:
        try:
            facts["workers"] = await stop_workers(procs)
        finally:
            await server.close()
    return facts


def run(project: Path, scratch: Path, shoot: Path | None = None) -> dict[str, Any]:
    """The acceptance scenario on ``project`` (build_scene's): the facts each test asserts. ``scratch``: a folder for
    the copy whose deck collider differs. ``shoot``: save the windows' pictures there."""
    from mesh_net.scene_room import disposable_project
    from mesh_net.world import World

    raised = scratch / "raised"
    shutil.copytree(project, raised, ignore=shutil.ignore_patterns(".mesh"))
    (raised / BRIDGE_GLB).write_bytes(raised_collider((project / BRIDGE_GLB).read_bytes(), DECK_NODE))
    with disposable_project(project_files(project), scaffold=False) as root:
        world = World(root)  # (the authority's own copy of the files)
    facts: dict[str, Any] = asyncio.run(_scenario(world, project, raised, shoot))
    return facts


# ------------------------------------------------------------------------------------------------------- the evidence
MOMENTS = [
    ("01_start", "both players at the start, on the ground"),
    ("02_a_on_deck", "A has climbed the west stairs onto the deck (2 m); B on the ground"),
    ("02_b_on_deck", "A back down; B on the deck"),
    ("03_a_over_b_under", "A on the deck, B directly beneath it on the ground (after walking through)"),
    ("04_a_struck_from_deck", "A struck at the bandit beneath from the deck: it stands, its HP unchanged"),
    ("05_a_reached_for_loot", "B felled the bandit; A reached for its loot from the deck: the loot stays"),
    ("06_b_took_loot", "B took the loot on the ground"),
    ("07_a_over_door", "A walked over the door beneath, on the deck: no transfer"),
    ("08_b_through_door", "B walked into the door on the ground: B's window shows the Start room; A's sees B gone"),
]


def _labelled(a: Any, b: Any, text: str) -> Any:
    from PIL import Image, ImageDraw

    pair = Image.new("RGB", (a.width + b.width + 4, a.height + 18), (20, 20, 24))
    pair.paste(a, (0, 18))
    pair.paste(b, (a.width + 4, 18))
    draw = ImageDraw.Draw(pair)
    draw.text((4, 3), f"window A | {text}", fill=(235, 235, 235))
    draw.text((a.width + 8, 3), "window B", fill=(235, 235, 235))
    return pair


def compose(raw: Path, out: Path, facts: dict[str, Any]) -> list[str]:
    """Each key moment as one picture, window A beside window B (palette PNG), and the pass beneath as a GIF."""
    from PIL import Image

    out.mkdir(parents=True, exist_ok=True)
    written = []
    for label, text in MOMENTS:
        with Image.open(raw / f"{label}-a.png") as a, Image.open(raw / f"{label}-b.png") as b:
            pair = _labelled(a.convert("RGB"), b.convert("RGB"), text)
        pair.quantize(colors=256, method=Image.Quantize.MEDIANCUT).save(out / f"{label}.png", optimize=True)
        written.append(f"{label}.png")
    seq = sorted({f.rsplit("-", 1)[0] for f in facts["frames"] if f.startswith("seq_")})
    gif = []
    for i, label in enumerate(seq):
        with Image.open(raw / f"{label}-a.png") as a, Image.open(raw / f"{label}-b.png") as b:
            half = [im.convert("RGB").resize((im.width // 2, im.height // 2), Image.Resampling.LANCZOS) for im in (a, b)]
        gif.append(_labelled(half[0], half[1], f"B passes beneath A {i + 1}/{len(seq)}").quantize(colors=256))
    gif[0].save(out / "seq_b_passes_beneath_a.gif", save_all=True, append_images=gif[1:], duration=250, loop=0,
                optimize=True)
    written.append("seq_b_passes_beneath_a.gif")
    return written


def main() -> None:
    import argparse
    import platform
    import tempfile
    import time

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path, help="where the evidence goes (docs/reviews/m3_two_client)")
    parser.add_argument("--work", type=Path, help="keep the built project and raw frames here (default: a temp folder)")
    args = parser.parse_args()
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    with tempfile.TemporaryDirectory(prefix="m3-evidence-") as temp:
        work = (args.work or Path(temp)).resolve()
        work.mkdir(parents=True, exist_ok=True)
        os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(work / "user_settings.json")  # (never a checkout's own file)
        t0 = time.perf_counter()
        project = build_scene(work)
        raw = work / "raw"
        raw.mkdir()
        facts = run(project, work, raw)
        seconds = round(time.perf_counter() - t0, 1)
        (work / "facts.json").write_text(json.dumps(facts, indent=1), encoding="utf-8")  # (kept with --work)
        import tests.test_mesh_net_hd2d_gpu as acceptance  # the run is kept only if the acceptance holds for it

        checks = sorted(n for n in dir(acceptance) if n.startswith("test_"))
        for name in checks:
            getattr(acceptance, name)(facts)
        written = compose(raw, args.out, facts)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    gl = facts["b"]["look"]["a"]["gl"]
    record = {"commit": commit, "gl": gl, "os": platform.platform(terse=True), "python": platform.python_version(),
              "build_and_run_s": seconds, "checks_passed": checks, "files": written}
    (args.out / "run.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    (args.out / "facts.json").write_text(json.dumps({k: v for k, v in facts.items() if k != "frames"}, indent=1) + "\n",
                                         encoding="utf-8")
    print(json.dumps(record, indent=1))


if __name__ == "__main__":
    main()
