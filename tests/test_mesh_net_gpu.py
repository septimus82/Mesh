"""Two independent real Mesh windows, a real loopback server and rendered avatars."""

import asyncio
import json
import os
import sys

import pytest

from mesh_net.server import Server

pytestmark = [pytest.mark.integration, pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1",
             reason="requires real Mesh windows (set MESH_GL_SMOKE=1)")]


async def command(proc, cmd):
    proc.stdin.write((cmd + "\n").encode())
    await proc.stdin.drain()
    async with asyncio.timeout(90):
        while line := await proc.stdout.readline():
            if line.startswith(b"NET_PROOF "):
                return json.loads(line[len(b"NET_PROOF "):])
        raise RuntimeError(f"window process exited with {await proc.wait()}")


async def observe(proc, predicate):
    async with asyncio.timeout(10):
        while True:
            reply = await command(proc, "state")
            if reply["state"] and predicate(reply["state"]):
                return reply
            await asyncio.sleep(0.025)


def test_independent_mesh_windows_share_motion_and_resume():
    async def run():
        server = Server()
        port = await server.start()
        procs = []
        try:
            for _ in range(2):
                procs.append(await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "tooling.net_window_probe", str(port),
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE))
            a, b = procs
            await asyncio.gather(*(command(p, "state") for p in procs))
            first, second = await asyncio.gather(*(observe(p, lambda s: len(s["players"]) == 2) for p in procs))
            aid, bid = first["entity"], second["entity"]
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
            await observe(a, lambda s: len(s["players"]) == 1)
            assert (await command(a, "capture"))["avatars"] == [True, False]
            await command(b, "press R")
            joined = await observe(b, lambda s: len(s["players"]) == 2)
            assert joined["entity"] != bid and [joined["entity"], *saved] in joined["state"]["players"]
            await observe(a, lambda s: s["players"] == joined["state"]["players"])
        finally:
            for proc in procs:
                if proc.returncode is None:
                    proc.stdin.close()
            for proc in procs:
                try:
                    await asyncio.wait_for(proc.wait(), 8)
                except TimeoutError:
                    proc.kill()
                    await proc.wait()
            await server.close()
    asyncio.run(run())
