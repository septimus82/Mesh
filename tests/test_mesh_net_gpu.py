"""Two independent real Mesh windows, a real loopback server and rendered avatars."""

import asyncio
import json
import os
import sys
from collections import defaultdict, deque

import pytest

from mesh_net.server import Server

pytestmark = pytest.mark.integration
worker_logs = defaultdict(lambda: deque(maxlen=30))


async def command(proc, cmd):
    proc.stdin.write((cmd + "\n").encode())
    await proc.stdin.drain()
    async with asyncio.timeout(90):
        while line := await proc.stdout.readline():
            if line.startswith(b"NET_PROOF "):
                return json.loads(line[len(b"NET_PROOF "):])
            worker_logs[proc].append(line.decode(errors="replace").rstrip())
        raise RuntimeError(f"window process exited with {await proc.wait()}: {list(worker_logs[proc])}")


async def observe(proc, predicate):
    reply = None
    try:
        async with asyncio.timeout(10):
            while True:
                reply = await command(proc, "state")
                if reply["state"] and predicate(reply["state"]):
                    return reply
                await asyncio.sleep(0.025)
    except TimeoutError as exc:
        raise AssertionError(f"state condition at line {predicate.__code__.co_firstlineno} "
                             f"not reached; last response: {reply}") from exc


async def stop_workers(procs):
    problems = []
    for proc in procs:
        if proc.stdin and not proc.stdin.is_closing():
            if proc.returncode is None:
                try:
                    proc.stdin.write(b"quit\n")
                    await proc.stdin.drain()
                except OSError:
                    pass
            proc.stdin.close()
    for proc in procs:
        reader = asyncio.create_task(proc.stdout.read())
        try:
            await asyncio.wait_for(proc.wait(), 8)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            problems.append("worker timed out and was killed")
        output = await reader
        if proc.returncode != 0:
            problems.append(f"worker exited {proc.returncode}: {list(worker_logs[proc])}, {output[-2000:]!r}")
    return problems


def require_clean_workers(problems):
    if problems:
        raise AssertionError("; ".join(problems))


def test_worker_exit_failure_is_detected():
    async def run():
        proc = await asyncio.create_subprocess_exec(sys.executable, "-c", "raise SystemExit(23)",
                                                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        with pytest.raises(AssertionError, match="exited 23"):
            require_clean_workers(await stop_workers([proc]))
    asyncio.run(run())


@pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1",
                    reason="requires real Mesh windows (set MESH_GL_SMOKE=1)")
def test_independent_mesh_windows_share_motion_and_resume():
    async def run():
        server = Server()
        port = await server.start()
        procs = []
        try:
            for _ in range(2):
                procs.append(await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "tooling.net_window_probe", str(port),
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT))
            a, b = procs
            await asyncio.gather(*(command(p, "state") for p in procs))
            first, second = await asyncio.gather(*(observe(p, lambda s: len(s["players"]) == 2) for p in procs))
            aid, bid = first["entity"], second["entity"]
            await command(a, "press SPACE")
            await observe(b, lambda s: s["enemy_hp"] == 1)
            await command(b, "press SPACE")
            await observe(a, lambda s: s["enemy_hp"] == 0 and s["pickup"])
            await command(b, "press E")
            await observe(a, lambda s: not s["pickup"] and s["holder"] == bid)
            starts = {eid: (x, y) for eid, x, y in first["state"]["players"]}
            await command(a, "press RIGHT")
            await observe(b, lambda s: any(i == aid and x > starts[i][0] for i, x, _ in s["players"]))
            await command(a, "release RIGHT")
            await command(b, "press UP")
            await observe(a, lambda s: any(i == bid and y > starts[i][1] for i, _, y in s["players"]))
            await command(b, "release UP")
            # Wait past the movement lease and interpolation delay; stable positions must agree.
            current = server.room.tick
            await observe(b, lambda s: s["tick"] >= current + 8)
            for proc in procs:
                capture = await command(proc, "capture")
                assert capture["avatars"] == [True, True] and capture["sign"]
                assert capture["state"]["players"] == server.room.snapshot()["players"]
            assert server.room.players[aid].y == starts[aid][1] and server.room.players[bid].x == starts[bid][0]
            saved = [server.room.players[bid].x, server.room.players[bid].y]
            await command(b, "press F2")
            left = None
            try:
                async with asyncio.timeout(10):
                    while (left := await command(b, "state"))["entity"] is not None:
                        await asyncio.sleep(0.025)
            except TimeoutError as exc:
                raise AssertionError(f"window did not disconnect: {left}") from exc
            await observe(a, lambda s: len(s["players"]) == 1)
            assert (await command(a, "capture"))["avatars"] == [True, False]
            await command(b, "press R")
            joined = await observe(b, lambda s: len(s["players"]) == 2)
            assert joined["state"]["enemy_hp"] == 0 and not joined["state"]["pickup"]
            assert joined["state"]["holder"] == joined["entity"]
            assert joined["entity"] != bid and [joined["entity"], *saved] in joined["state"]["players"]
            await observe(a, lambda s: s["players"] == joined["state"]["players"])
        finally:
            try:
                problems = await stop_workers(procs)
            finally:
                await server.close()
            error = sys.exc_info()[1]
            if error is None:
                require_clean_workers(problems)
            elif problems:
                error.add_note("window cleanup: " + "; ".join(problems))
    asyncio.run(run())


def _scene_room():
    from mesh_net.scene_room import COOP_SCENE, SceneRoom, coop_files, disposable_project

    with disposable_project(coop_files(), scaffold=False) as root:
        return SceneRoom(root / COOP_SCENE, root)


@pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1",
                    reason="requires real Mesh windows (set MESH_GL_SMOKE=1)")
def test_two_windows_play_the_studio_scene_together():
    """N6: two hidden Mesh windows load the co-op scene, share movement, the lever and gate, the bandit and its
    loot through one authority, and render each other through the scene renderer and camera."""
    lever, gate, bandit = "start_gate_lever_352_352_0_0", "start_gate_432_256_0_0", "start_bandit_608_256_0_0"

    def pos(state, eid):
        return next(r[1:3] for r in state["players"] if r[0] == eid)

    async def hold(proc, key, observer, predicate):
        await command(proc, f"press {key}")
        try:
            return await observe(observer, predicate)
        finally:
            await command(proc, f"release {key}")

    async def tap(proc, key):
        await command(proc, f"press {key}")
        await command(proc, f"release {key}")

    async def run():
        room = _scene_room()
        server = Server(room)
        port = await server.start()
        procs = []
        try:
            for _ in range(2):
                procs.append(await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "tooling.net_scene_probe", str(port),
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT))
            a, b = procs
            first, second = await asyncio.gather(*(observe(p, lambda s: len(s["players"]) == 2) for p in procs))
            aid, bid = first["entity"], second["entity"]
            assert first["identity"] == second["identity"] == room.identity

            tiles = sorted([t.center_x, t.center_y, t.width, t.height] for t in room.scenery)
            bodies = {i: room.doors[i][0] for i in room.doors} | {i: e.body for i, e in room.enemies.items()}
            for proc, own, peer in ((a, aid, bid), (b, bid, aid)):
                shot = await command(proc, "capture")
                assert shot["tiles"] == tiles  # the authority blocks exactly where the window's map does
                for i, body in bodies.items():
                    assert shot["objects"][i][:4] == [body.center_x, body.center_y, body.width, body.height]
                assert shot["players"] == sorted([f"net_player_{aid}", f"net_player_{bid}"])  # template gone
                assert shot["drawn"][str(own)] > 0 and shot["drawn"][str(peer)] > 0
                assert shot["avatars"][str(own)][2:4] == [room.players[own].body.width, room.players[own].body.height]
                assert shot["avatars"][str(own)][4] == [255, 255, 255] and shot["avatars"][str(peer)][4] != [255, 255, 255]
                assert shot["behaviours"][f"net_player_{own}"] == ["CameraFollowBehaviour", "SpriteAnimatorBehaviour"]
                assert shot["behaviours"][f"net_player_{peer}"] == ["SpriteAnimatorBehaviour"]
                assert shot["behaviours"][bandit] == ["SpriteAnimatorBehaviour"] and lever not in shot["behaviours"]

            # Movement: A walks into the locked gate; B sees it stop where the server stopped it.
            camera = (await command(a, "capture"))["camera"]
            await hold(a, "RIGHT", b, lambda s: pos(s, aid)[0] >= 390)
            await observe(b, lambda s: pos(s, aid)[0] == 390.5)
            moved = await command(a, "capture")
            assert moved["camera"][0] > camera[0] and moved["drawn"][str(aid)] > 0  # the scene camera followed

            # Interaction: A pulls the lever; both see the gate open.
            await hold(a, "UP", a, lambda s: pos(s, aid)[1] >= 320)
            await hold(a, "LEFT", a, lambda s: pos(s, aid)[0] <= 372)
            await tap(a, "E")
            await asyncio.gather(*(observe(p, lambda s: s["open"] == [gate] and s["used"] == [lever]) for p in procs))
            for proc in procs:
                assert (await command(proc, "capture"))["objects"][gate][4] is False

            # Combat: both reach the bandit and strike it; the server's HP, death and loot reach both windows.
            await hold(a, "DOWN", a, lambda s: pos(s, aid)[1] <= 262)
            await hold(a, "RIGHT", a, lambda s: pos(s, aid)[0] >= 575)
            await hold(b, "RIGHT", b, lambda s: pos(s, bid)[0] >= 560)
            await tap(a, "SPACE")
            await observe(b, lambda s: s["enemies"] == [[bandit, 2.0]])
            await tap(b, "SPACE")
            await observe(a, lambda s: s["enemies"] == [[bandit, 1.0]])
            ready = room.tick + room.cooldown
            await observe(a, lambda s: s["tick"] >= ready)
            await tap(a, "SPACE")
            await asyncio.gather(*(observe(p, lambda s: s["enemies"] == [[bandit, 0.0]] and s["drops"] == [bandit])
                                   for p in procs))
            for proc in procs:
                shot = await command(proc, "capture")
                assert shot["objects"][bandit][4] is False and shot["drops"] == [bandit]
            await tap(b, "E")
            await asyncio.gather(*(observe(p, lambda s: s["loot"] == [[bandit, bid]] and not s["drops"]) for p in procs))

            # Disconnect and resume: one avatar each way, never a duplicate; the loot follows the character.
            await command(b, "press F2")
            await observe(a, lambda s: [r[0] for r in s["players"]] == [aid])
            alone = await command(a, "capture")
            assert alone["players"] == [f"net_player_{aid}"] and list(alone["drawn"]) == [str(aid)]
            await command(b, "release F2")
            await tap(b, "R")
            back = await observe(b, lambda s: len(s["players"]) == 2)
            assert back["entity"] not in (aid, bid) and back["state"]["loot"] == [[bandit, back["entity"]]]
            await observe(a, lambda s: s["players"] == back["state"]["players"] or s["tick"] > back["state"]["tick"])
            for proc in procs:
                shot = await command(proc, "capture")
                assert shot["players"] == sorted([f"net_player_{aid}", f"net_player_{back['entity']}"])
                assert all(n > 0 for n in shot["drawn"].values()) and len(shot["drawn"]) == 2
        finally:
            try:
                problems = await stop_workers(procs)
            finally:
                await server.close()
            error = sys.exc_info()[1]
            if error is None:
                require_clean_workers(problems)
            elif problems:
                error.add_note("window cleanup: " + "; ".join(problems))
    asyncio.run(run())


@pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1",
                    reason="requires real Mesh windows (set MESH_GL_SMOKE=1)")
def test_two_windows_meet_party_travel_and_return():
    """N7: two hidden Mesh windows meet in the hub, form a party, travel into their own instance of Layer 1, open
    its gate, go down to Layer 2 and fight its guardian together, then one returns through Layer 1 to the hub while
    the other stays; that one drops and resumes. Every room is loaded by GameWindow.load_scene and drawn by the
    scene renderer and camera; the server owns all of it."""
    from mesh_net.scene_room import disposable_project
    from mesh_net.server import WorldServer
    from mesh_net.world import World, expedition_files

    hub, r1, r2 = "start", "ancient_ruins_layer_1", "ancient_ruins_layer_2"
    gate1, lever1, guardian = f"{r1}_gate_432_256_0_0", f"{r1}_lever_352_352_0_0", f"{r2}_guardian_480_256_0_0"

    def own(reply):
        return next(r[1:3] for r in reply["state"]["players"] if r[0] == reply["entity"])

    async def until(proc, predicate, timeout=15):
        reply = None
        try:
            async with asyncio.timeout(timeout):
                while True:
                    reply = await command(proc, "state")
                    if reply["phase"] == "playing" and reply["state"] and predicate(reply):
                        return reply
                    await asyncio.sleep(0.025)
        except TimeoutError as exc:
            last = {k: reply[k] for k in ("phase", "key", "room", "entity", "loads")} if reply else {}
            if reply and reply["state"]:
                last["players"], last["tick"] = reply["state"]["players"], reply["state"]["tick"]
            last["server"] = {m.pid: (m.instance, m.eid, m.online) for m in world.members.values()}
            last["transfers"] = list(world.transfers)
            last["server_ticks"] = {i: (inst.room.tick, {e: (p.body.center_x, p.body.center_y, p.seq, p.last_input)
                                                         for e, p in inst.room.players.items()})
                                    for i, inst in world.instances.items()}
            raise AssertionError(f"condition at line {predicate.__code__.co_firstlineno} not reached; last: {last}") from exc

    async def hold(proc, key, predicate):
        await command(proc, f"press {key}")
        try:
            return await until(proc, predicate)
        finally:
            await command(proc, f"release {key}")

    async def tap(proc, key):
        await command(proc, f"press {key}")
        await command(proc, f"release {key}")

    async def go(proc, key, target):
        """Walk to ``target`` along the key's axis: held while far (a held key's release lands a few ticks late),
        then in steps of a tick or two."""
        axis, sign = {"RIGHT": (0, 1), "LEFT": (0, -1), "UP": (1, 1), "DOWN": (1, -1)}[key]

        def short(r, margin=0.0):
            return (target - own(r)[axis]) * sign > margin

        reply = await until(proc, lambda r: True)
        if short(reply, 60):
            await hold(proc, key, lambda r: not short(r, 60))
        for _ in range(40):
            reply = await until(proc, lambda r: True)
            if not short(reply):
                return reply
            tick = reply["state"]["tick"]
            await command(proc, f"press {key}")
            await until(proc, lambda r: r["state"]["tick"] > tick)
            await command(proc, f"release {key}")
        raise AssertionError(f"{key} to {target} not reached: {own(reply)}")

    async def shot(proc, players):
        """What the window rendered: its own room's scene, exactly these avatars drawn, the camera on its own."""
        reply = await command(proc, "capture")
        assert reply["scene_path"] == world.defs[reply["key"]].path and reply["shown"] == reply["room"]
        assert sorted(int(e) for e in reply["drawn"]) == sorted(players) and all(reply["drawn"].values())
        cx, cy = reply["camera"]
        x, y = own(reply)
        assert abs(cx - x) < 330 and abs(cy - y) < 190  # the scene camera follows the window's own avatar
        return reply

    with disposable_project(expedition_files(), scaffold=False) as root:
        world = World(root)

    async def run():
        server = WorldServer(world)
        port = await server.start()
        procs = []
        try:
            for _ in range(2):
                procs.append(await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "tooling.net_world_probe", str(port),
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT))
            a, b = procs
            first, second = await asyncio.gather(*(until(p, lambda r: len(r["state"]["players"]) == 2) for p in procs))
            assert first["identity"] == second["identity"] == world.identity and first["key"] == second["key"] == hub

            # The hub: a creates a party and invites the nearest player; b accepts.
            await tap(a, "P")
            await until(a, lambda r: r["party"] and r["party"]["party"])
            await tap(a, "I")
            await until(b, lambda r: r["party"]["invites"])
            await tap(b, "Y")
            for proc in procs:
                await until(proc, lambda r: len(r["party"]["members"]) == 2)

            # Both walk into the hub's door: their party's own Layer 1, at its arrival marker.
            await asyncio.gather(*(hold(p, "RIGHT", lambda r: r["key"] == r1) for p in procs))
            ra, rb = await asyncio.gather(*(until(p, lambda r: len(r["state"]["players"]) == 2) for p in procs))
            assert ra["room"] == rb["room"] and ra["room"] in world.instances and world.instances[ra["room"]].party
            for proc in procs:
                await shot(proc, [ra["entity"], rb["entity"]])

            # Interaction: a opens Layer 1's gate with its lever; both see it open.
            await go(a, "RIGHT", 352)
            await go(a, "UP", 300)
            await tap(a, "E")
            for proc in procs:
                await until(proc, lambda r: r["state"]["open"] == [gate1] and r["state"]["used"] == [lever1])
                assert (await command(proc, "capture"))["objects"][gate1][4] is False

            # Both go down to Layer 2 through the open gate.
            await go(a, "DOWN", 258)
            await go(b, "RIGHT", 250)
            await go(b, "UP", 254)
            await asyncio.gather(*(hold(p, "RIGHT", lambda r: r["key"] == r2) for p in procs))
            ra, rb = await asyncio.gather(*(until(p, lambda r: len(r["state"]["players"]) == 2) for p in procs))
            assert ra["room"] == rb["room"] and ra["state"]["used"] == [] and ra["state"]["open"] == []  # its own

            # Combat: both strike Layer 2's guardian; its HP, death and drop reach both windows.
            for proc in procs:
                await go(proc, "RIGHT", 430)
                await go(proc, "UP", 236)  # the guardian's feet (its collider) are at y 232-244: strike level with them
                await hold(proc, "RIGHT", lambda r: next(x for x in r["state"]["players"] if x[0] == r["entity"])[3] == 0)
            await tap(a, "SPACE")
            await until(b, lambda r: r["state"]["enemies"] == [[guardian, 1.0]])
            await tap(b, "SPACE")
            for proc in procs:
                await until(proc, lambda r: r["state"]["enemies"] == [[guardian, 0.0]] and r["state"]["drops"] == [guardian])
                assert (await command(proc, "capture"))["drops"] == [guardian]

            # a returns to Layer 1 (b stays): each window shows only its own room's players.
            await hold(a, "LEFT", lambda r: r["key"] == r1)
            await until(b, lambda r: len(r["state"]["players"]) == 1)
            la = await until(a, lambda r: len(r["state"]["players"]) == 1)
            assert la["state"]["open"] == [gate1]  # Layer 1 as the party left it
            await shot(a, [la["entity"]])
            await shot(b, [rb["entity"]])
            # ... and on to the hub.
            await go(a, "LEFT", 600)
            await go(a, "UP", 254)
            home = await hold(a, "LEFT", lambda r: r["key"] == hub)
            assert own(home) == [704.0, 160.0] and [m[2] for m in home["party"]["members"]] == [hub, r2]
            await shot(a, [home["entity"]])

            # b drops and resumes: back in the party's Layer 2, the guardian still dead, the party intact.
            await command(b, "press F2")
            await until(a, lambda r: [m[1] for m in r["party"]["members"]] == [True, False])
            await command(b, "release F2")
            await tap(b, "R")
            back = await until(b, lambda r: r["key"] == r2 and len(r["state"]["players"]) == 1)
            assert back["room"] == rb["room"] and back["state"]["enemies"] == [[guardian, 0.0]]
            await until(a, lambda r: [m[1] for m in r["party"]["members"]] == [True, True])
            await shot(b, [back["entity"]])
        finally:
            try:
                problems = await stop_workers(procs)
            finally:
                await server.close()
            error = sys.exc_info()[1]
            if error is None:
                require_clean_workers(problems)
            elif problems:
                error.add_note("window cleanup: " + "; ".join(problems))
    asyncio.run(run())
