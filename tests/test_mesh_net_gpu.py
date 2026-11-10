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
