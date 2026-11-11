"""Two independent real Mesh windows, a real loopback server and rendered avatars."""

import asyncio
import json
import os
import sys
from collections import defaultdict, deque

import pytest

from mesh_net.server import Server
from tests.net_resume import drop_and_resume
from tests.net_walk import ABOVE, GAP, ON_ENEMY, walk

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
def test_two_windows_play_the_studio_scene_together(record_testsuite_property):
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

    walks = []  # every walk's legs: recorded (lane summary) to show how late releases land on each runner

    async def run():
        room = _scene_room()
        server = Server(room)
        port = await server.start()

        async def go(proc, eid, key, target, within):
            """tests/net_walk.walk: to ``target`` +- ``within`` by the server's own position, back after an overshoot."""
            async def where():
                body = room.players[eid].body
                return room.tick, body.center_x, body.center_y
            await walk(lambda cmd: command(proc, cmd), key, target, within, where, record=walks)

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
            # A goes through the gate's gap and steps down onto the bandit from above (its feet stop A at y 268,
            # facing it); B walks into it from the left along y 256.
            await go(a, aid, "DOWN", *GAP)
            await go(a, aid, "RIGHT", 520, 24)  # (past the gate, short of the bandit)
            await go(a, aid, "UP", *ABOVE)
            await go(a, aid, "RIGHT", 608, 16)
            await go(a, aid, "DOWN", *ON_ENEMY)
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
    try:
        asyncio.run(run())
    finally:
        record_testsuite_property("measure.net_walk_n6", json.dumps(walks))


@pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1",
                    reason="requires real Mesh windows (set MESH_GL_SMOKE=1)")
def test_two_windows_meet_party_travel_and_return(record_testsuite_property):
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
            last["trace"] = reply["trace"] if reply else None
            last["history"] = list(world.history)[-12:]
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

    pids = {}  # window -> its player id (the server's member)
    walks = []  # every walk's legs: recorded (lane summary) to show how late releases land on each runner

    async def go(proc, key, target, within):
        """tests/net_walk.walk: to ``target`` +- ``within`` by the server's own position, back after an overshoot."""
        async def where():
            m = world.members[pids[proc]]
            room = world.instances[m.instance or ""].room
            body = room.players[m.eid].body
            return room.tick, body.center_x, body.center_y
        await walk(lambda cmd: command(proc, cmd), key, target, within, where, record=walks)

    def facing(r):
        return next(x for x in r["state"]["players"] if x[0] == r["entity"])[3]  # 0 right, 1 up, 2 left, 3 down

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
            pids.update({a: first["player"], b: second["player"]})

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

            # Interaction: a opens Layer 1's gate with its lever (352, 352: in reach from here), facing it.
            await go(a, "RIGHT", 352, 16)
            await go(a, "UP", 300, 16)
            await hold(a, "UP", lambda r: facing(r) == 1)  # (a walk that stepped back down faces away)
            await tap(a, "E")
            for proc in procs:
                await until(proc, lambda r: r["state"]["open"] == [gate1] and r["state"]["used"] == [lever1])
                assert (await command(proc, "capture"))["objects"][gate1][4] is False

            # Both go down to Layer 2 through the open gate.
            await go(a, "DOWN", *GAP)
            await go(b, "RIGHT", 250, 40)
            await go(b, "UP", *GAP)
            await asyncio.gather(*(hold(p, "RIGHT", lambda r: r["key"] == r2) for p in procs))
            ra, rb = await asyncio.gather(*(until(p, lambda r: len(r["state"]["players"]) == 2) for p in procs))
            assert ra["room"] == rb["room"] and ra["state"]["used"] == [] and ra["state"]["open"] == []  # its own

            # Combat: both strike Layer 2's guardian; its HP, death and drop reach both windows. Each goes up past it
            # and steps down onto it from above: its feet (y 232-244) stop them at y 268, facing it.
            for proc in procs:
                await go(proc, "RIGHT", 430, 16)
                await go(proc, "UP", *ABOVE)
                await go(proc, "RIGHT", 480, 16)
                await go(proc, "DOWN", *ON_ENEMY)
                await until(proc, lambda r: facing(r) == 3)
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
            await go(a, "LEFT", 600, 40)
            await go(a, "UP", *GAP)
            home = await hold(a, "LEFT", lambda r: r["key"] == hub)
            assert own(home) == [704.0, 160.0]
            # (the enter and the party view are separate frames: the reply that first shows the hub can predate it)
            await until(a, lambda r: [m[2] for m in r["party"]["members"]] == [hub, r2])
            await shot(a, [home["entity"]])

            # b drops and resumes: back in the party's Layer 2, the guardian still dead, the party intact. (A key's
            # reply predates the key, and while F2 closes b still shows its old session: tests/net_resume.py.)
            def b_away():  # a sees b leave the party's game
                return until(a, lambda r: [m[1] for m in r["party"]["members"]] == [True, False])
            back = await drop_and_resume(lambda cmd: command(b, cmd), world, pids[b], rb["room"], away=b_away)
            assert back["room"] == rb["room"] and back["key"] == r2 and len(back["state"]["players"]) == 1
            assert back["state"]["enemies"] == [[guardian, 0.0]]
            await until(a, lambda r: [m[1] for m in r["party"]["members"]] == [True, True])
            await shot(b, [back["entity"]])
        finally:
            failure = sys.exc_info()[1]
            if failure is not None:  # what each window and the server last knew, timestamped
                for name, proc in zip("ab", procs):
                    try:
                        r = await asyncio.wait_for(command(proc, "state"), 5)
                        failure.add_note(f"window {name}: phase {r['phase']}, room {r['room']}, status {r['status']!r}, "
                                         f"trace {r['trace']}")
                    except Exception as exc:  # noqa: BLE001  # (a window that can't answer says so)
                        failure.add_note(f"window {name}: no answer ({exc!r})")
                failure.add_note(f"server history: {list(world.history)}")
            try:
                problems = await stop_workers(procs)
            finally:
                await server.close()
            error = sys.exc_info()[1]
            if error is None:
                require_clean_workers(problems)
            elif problems:
                error.add_note("window cleanup: " + "; ".join(problems))
    try:
        asyncio.run(run())
    finally:
        record_testsuite_property("measure.net_walk_n7", json.dumps(walks))


async def _state(proc, predicate, timeout=15, why=""):
    reply = None
    try:
        async with asyncio.timeout(timeout):
            while True:
                reply = await command(proc, "state")
                if predicate(reply):
                    return reply
                await asyncio.sleep(0.025)
    except TimeoutError as exc:
        last = {k: reply.get(k) for k in ("phase", "key", "room", "status", "refused", "sheet", "trace")} if reply else None
        raise AssertionError(f"{why or 'condition'} not reached; last: {last}") from exc


def _own(reply):
    return next(r[1:4] for r in reply["state"]["players"] if r[0] == reply["entity"])


async def _hold(proc, key, predicate, why=""):
    await command(proc, f"press {key}")
    try:
        return await _state(proc, lambda r: r["phase"] == "playing" and r["state"] and predicate(r), why=why)
    finally:
        await command(proc, f"release {key}")


async def _tap(proc, key):
    await command(proc, f"press {key}")
    await command(proc, f"release {key}")


async def _go(proc, key, target, within, walks):
    """tests/net_walk.walk on the window's copy of the server's snapshots (this test's server is another process)."""
    async def where():
        r = await _state(proc, lambda r: r["phase"] == "playing" and r["state"])
        x, y, _ = _own(r)
        return r["state"]["tick"], x, y
    await walk(lambda cmd: command(proc, cmd), key, target, within, where, record=walks)


async def _server(store, logs):
    """``python -m mesh_net.server --expedition --store STORE`` as its own process; returns (process, port)."""
    proc = await asyncio.create_subprocess_exec(sys.executable, "-m", "mesh_net.server", "--expedition", "--store",
                                                str(store), "--port", "0", stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.STDOUT)
    async with asyncio.timeout(60):
        while line := await proc.stdout.readline():
            text = line.decode(errors="replace").rstrip()
            logs.append(text)
            if "listening on 127.0.0.1:" in text:
                return proc, int(text.rsplit(":", 1)[1])
    raise RuntimeError(f"server did not start: {logs[-10:]}")


@pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1",
                    reason="requires real Mesh windows (set MESH_GL_SMOKE=1)")
def test_two_characters_persist_through_a_server_restart(tmp_path, record_testsuite_property):
    """N8: two characters (made with the admin store) play in two hidden Mesh windows against a real server process
    with a character store: party, Layer 1, Layer 2, the guardian struck by both, each takes their own sigil and
    earns the unlock. They leave; the server process is killed outright. The store, read directly, holds both
    characters' items and unlocks. A new server process on the same store takes both back as themselves (their
    windows show their items and unlock), to fresh rooms, and they set out on a new expedition."""
    from mesh_net.characters import CharacterStore

    r1, r2 = "ancient_ruins_layer_1", "ancient_ruins_layer_2"
    guardian, unlock = f"{r2}_guardian_480_256_0_0", "ruins_layer_2_completed"
    path = tmp_path / "characters.db"
    store = CharacterStore(path, create=True)
    keys = []
    for name in ("Ada", "Bo"):
        cid, key = store.create(name)
        keys.append((cid, tmp_path / f"{name}.json"))
        keys[-1][1].write_text(json.dumps({"id": cid, "key": key}), encoding="utf-8")
    store.close()
    logs: list[str] = []
    walks: list = []  # every walk's legs: recorded (lane summary) to show how late releases land on each runner

    async def window(port, key_file):
        return await asyncio.create_subprocess_exec(sys.executable, "-m", "tooling.net_world_probe", str(port),
                                                    str(key_file), stdin=asyncio.subprocess.PIPE,
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)

    async def run():
        server, port = await _server(path, logs)
        procs = []
        try:
            procs = [await window(port, key_file) for _, key_file in keys]
            a, b = procs
            playing = lambda r: r["phase"] == "playing" and r["state"] and r["sheet"]  # noqa: E731
            ra, rb = [await _state(p, lambda r: playing(r) and len(r["state"]["players"]) == 2, why="both in the hub")
                      for p in procs]
            assert {ra["sheet"]["name"], rb["sheet"]["name"]} == {"Ada", "Bo"} and ra["sheet"]["items"] == []

            await _tap(a, "P")
            await _state(a, lambda r: r["party"] and r["party"]["party"], why="party made")
            await _tap(a, "I")
            await _state(b, lambda r: r["party"] and r["party"]["invites"], why="invitation")
            await _tap(b, "Y")
            for p in procs:
                await _state(p, lambda r: r["party"] and len(r["party"]["members"]) == 2, why="party of two")
            await asyncio.gather(*(_hold(p, "RIGHT", lambda r: r["key"] == r1, why="into Layer 1") for p in procs))
            await _go(a, "RIGHT", 352, 16, walks)
            await _go(a, "UP", 300, 16, walks)
            await _hold(a, "UP", lambda r: _own(r)[2] == 1, why="facing the lever")  # (if the walk stepped back down)
            await _tap(a, "E")
            for p in procs:
                await _state(p, lambda r: playing(r) and r["state"]["open"], why="gate open")
            await _go(a, "DOWN", *GAP, walks)
            await _go(b, "RIGHT", 250, 40, walks)
            await _go(b, "UP", *GAP, walks)
            await asyncio.gather(*(_hold(p, "RIGHT", lambda r: r["key"] == r2, why="into Layer 2") for p in procs))
            for p in procs:
                await _go(p, "RIGHT", 430, 16, walks)  # (up past the guardian, then down onto it: as N7's test)
                await _go(p, "UP", *ABOVE, walks)
                await _go(p, "RIGHT", 480, 16, walks)
                await _go(p, "DOWN", *ON_ENEMY, walks)
                await _state(p, lambda r: r["phase"] == "playing" and r["state"] and _own(r)[2] == 3, why="facing it")
            await _tap(a, "SPACE")
            await _state(b, lambda r: playing(r) and r["state"]["enemies"] == [[guardian, 1.0]], why="first hit")
            await _tap(b, "SPACE")
            for p in procs:  # both were there: both earn the unlock, both may take their own sigil
                await _state(p, lambda r: playing(r) and unlock in r["sheet"]["unlocks"] and r["sheet"]["loot"],
                             why="unlock and loot")
                await _tap(p, "E")
                got = await _state(p, lambda r: playing(r) and r["sheet"]["items"] == [["guardian_sigil", 1]],
                                   why="sigil taken")
                assert got["sheet"]["loot"] == [] and (await command(p, "capture"))["drops"] == [guardian]

            for p in procs:  # both leave, then the server goes down hard
                await _tap(p, "F2")
                await _state(p, lambda r: r["phase"] == "disconnected", why="left")
            server.kill()
            await server.wait()
            check = CharacterStore(path)  # what the store holds, not what the clients said
            try:
                for cid, _ in keys:
                    state = check.load(cid)
                    assert state.items == (("guardian_sigil", 1),) and state.unlocks == (unlock,) and state.completed == 1
            finally:
                check.close()

            server, port = await _server(path, logs)
            for p in procs:  # the windows join the new server as their characters (N: a fresh join, not a resume)
                await command(p, f"port {port}")
                await _tap(p, "N")
            back = [await _state(p, lambda r: playing(r) and r["key"] == "start" and len(r["state"]["players"]) == 2,
                                 why="back in the hub") for p in procs]
            for reply, (cid, _) in zip(back, keys):
                assert reply["sheet"]["id"] == cid and reply["sheet"]["items"] == [["guardian_sigil", 1]]
                assert reply["sheet"]["unlocks"] == [unlock] and reply["room"] == "start:1"  # fresh rooms
                shot = await command(procs[back.index(reply)], "capture")
                assert len(shot["drawn"]) == 2 and all(shot["drawn"].values())
            await _tap(a, "P")
            await _state(a, lambda r: r["party"] and r["party"]["party"], why="new party")
            await _tap(a, "I")
            await _state(b, lambda r: r["party"] and r["party"]["invites"], why="new invitation")
            await _tap(b, "Y")
            await asyncio.gather(*(_hold(p, "RIGHT", lambda r: r["key"] == r1, why="a new expedition") for p in procs))
            fresh = await _state(a, lambda r: playing(r) and r["key"] == r1, why="in the new Layer 1")
            assert fresh["state"]["open"] == [] and fresh["sheet"]["unlocks"] == [unlock]
        finally:
            failure = sys.exc_info()[1]
            if failure is not None:
                failure.add_note(f"server log: {logs[-20:]}")
            try:
                problems = await stop_workers(procs)
            finally:
                if server.returncode is None:
                    server.kill()
                    await server.wait()
            if failure is None:
                require_clean_workers(problems)
            elif problems:
                failure.add_note("window cleanup: " + "; ".join(problems))
    try:
        asyncio.run(run())
    finally:
        record_testsuite_property("measure.net_walk_n8", json.dumps(walks))
