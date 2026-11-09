from __future__ import annotations

import asyncio

import pytest

from mesh_net import protocol as wire
from mesh_net.client import connect
from mesh_net.server import Server
from mesh_net.simulation import Room


def intent(eid, seq, dx=1, dy=0):
    return {"v": 1, "type": "input", "entity": eid, "seq": seq, "dx": dx, "dy": dy}


@pytest.mark.fast
def test_step_owns_distance_and_old_inputs_expire():
    room = Room()
    eid = room.join()
    start = room.players[eid].x
    for seq in range(1, 7):
        room.input(eid, intent(eid, seq))
    room.input(eid, intent(eid, 6, -1))
    room.input(eid, intent(eid, 3, -1))
    assert room.players[eid].x == start
    room.step()
    assert room.players[eid].x == start + 4
    for _ in range(20):
        room.step()
    assert room.players[eid].x == start + 20
    for invalid in [intent(eid + 1, 7), intent(eid, True), intent(eid, 7, 9), intent(eid, 7, 1, 1),
                    {**intent(eid, 7), "x": 10}, {**intent(eid, 7), "v": 2}]:
        with pytest.raises(wire.Invalid):
            room.input(eid, invalid)


async def until(client, predicate):
    async with asyncio.timeout(3):
        while True:
            state = await client.receive()
            if predicate(state):
                return state


@pytest.mark.integration
def test_two_sockets_move_disconnect_resume_and_shutdown():
    async def run():
        server = Server()
        port = await server.start()
        try:
            async with connect(port) as a:
                async with connect(port) as b:
                    assert a.session != b.session and a.entity != b.entity
                    x, y = server.room.players[b.entity].x, server.room.players[b.entity].y
                    await b.input(0, 1)
                    state = await until(a, lambda s: any(i == b.entity and py > y for i, _, py in s["players"]))
                    assert state["players"][0][1:] == [200, 135]
                    assert state["players"][1][1] == x
                    old = b.resume
                await until(a, lambda s: len(s["players"]) == 1)
                async with connect(port, old) as c:
                    assert c.entity != b.entity and c.session != b.session and c.resume != old
                    assert c.state["players"][-1][2] > y
                    with pytest.raises((EOFError, OSError)):
                        async with connect(port, old):
                            pytest.fail("reused credential")
                    c.writer.write(wire.encode(intent(b.entity, 1)))
                    await until(a, lambda s: len(s["players"]) == 1)
                await server.close()
                with pytest.raises((EOFError, OSError)):
                    await until(a, lambda s: False)
        finally:
            await server.close()
        assert not server.connections and not server.peers and not server.offline
    asyncio.run(run())


@pytest.mark.integration
def test_bad_frames_close_only_the_offender():
    async def run():
        server = Server()
        port = await server.start()
        try:
            async with connect(port) as survivor:
                for data in [b'{"v":1,"type":"join","resume":null,"resume":null}\n', b'[]\n', b'\xff\n',
                             b'[' * 1500 + b']' * 1500 + b'\n', b'x' * (wire.MAX_BYTES + 1) + b'\n']:
                    reader, writer = await asyncio.open_connection("127.0.0.1", port)
                    try:
                        writer.write(data)
                        assert await asyncio.wait_for(reader.read(1), 2) == b""
                    finally:
                        writer.close()
                        await writer.wait_closed()
                assert len((await survivor.receive())["players"]) == 1
        finally:
            await server.close()
    asyncio.run(run())

@pytest.mark.integration
def test_server_process_killed_mid_session_reaches_eof():
    import sys

    async def run():
        proc = await asyncio.create_subprocess_exec(sys.executable, "-m", "mesh_net.server", "--port", "0",
                                                    stdout=asyncio.subprocess.PIPE)
        try:
            banner = await asyncio.wait_for(proc.stdout.readline(), 5)
            port = int(banner.rsplit(b":", 1)[1])
            async with connect(port) as client:
                proc.kill()
                await asyncio.wait_for(proc.wait(), 5)
                with pytest.raises((EOFError, OSError)):
                    await until(client, lambda s: False)
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
    asyncio.run(run())
