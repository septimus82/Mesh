"""Wire protocol v2 (owner decision D1, M3-2): a peer of another version is refused at the handshake with a reason, in
either direction, with no downgrade; JSON's NaN and Infinity never reach a check; a 2D room's rows carry elevation 0
and no floor; and a client never applies a snapshot older than the last. (The HD-2D rows: tests/test_mesh_net_hd2d.py.)"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from mesh_net import protocol as wire
from mesh_net.client import Client, connect
from mesh_net.scene_room import COOP_SCENE, SceneRoom, check_state, coop_files, disposable_project
from mesh_net.server import Server, WorldServer
from mesh_net.world import World, check_welcome, expedition_files, welcome

pytestmark = pytest.mark.integration  # (sockets, rooms built in folders)

V1_JOIN = b'{"v":1,"type":"join","resume":null}\n'
REFUSED = {"v": 2, "type": "refused", "code": "protocol_version"}


@pytest.fixture(scope="module")
def coop() -> SceneRoom:
    with disposable_project(coop_files(), scaffold=False) as root:
        return SceneRoom(root / COOP_SCENE, root)


@pytest.mark.parametrize("version", [1, 3, 0, "2", 2.0, True, None])
def test_every_frame_of_another_version_is_refused_as_such(version: Any) -> None:
    msg = {"v": version, "type": "join", "resume": None}
    with pytest.raises(wire.VersionMismatch, match="speaks version 2 only"):
        wire.fields(msg, "join", "resume")
    wire.fields({**msg, "v": 2}, "join", "resume")
    assert wire.VERSION == 2


def test_a_frame_without_a_version_is_malformed_not_another_version(coop: SceneRoom) -> None:
    """No ``v`` at all is a malformed frame (wire.Invalid): the server closes without a protocol_version refusal."""
    with pytest.raises(wire.Invalid) as refused:
        wire.fields({"type": "join", "resume": None}, "join", "resume")
    assert not isinstance(refused.value, wire.VersionMismatch)

    async def run() -> None:
        server = Server(coop)
        port = await server.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port, limit=wire.MAX_BYTES)
            try:
                writer.write(b'{"type":"join","resume":null}\n')
                assert await asyncio.wait_for(reader.read(1), 2) == b"", "closed, nothing said"
            finally:
                writer.close()
                await writer.wait_closed()
        finally:
            await server.close()

    asyncio.run(run())


def test_a_disconnect_says_why() -> None:
    """The window's caption after a session ends: a refusal's own words, else the error's kind."""
    from mesh_net.demo import reason

    mismatch = None
    try:
        wire.fields({"v": 1, "type": "welcome"}, "welcome")
    except wire.VersionMismatch as exc:
        mismatch = exc
    assert mismatch is not None and reason(mismatch) == "protocol version 1: this Mesh speaks version 2 only"
    assert reason(wire.Invalid("refused (protocol_version)")) == "refused (protocol_version)"
    assert reason(asyncio.IncompleteReadError(b"", None)) == "IncompleteReadError"
    assert len(reason(wire.Invalid("x" * 500))) == 64


def test_a_v1_client_is_refused_by_a_v2_server_with_a_reason(coop: SceneRoom) -> None:
    """N6 and N7: a v1 join is answered with ``refused`` (code protocol_version) and the connection closed; nobody
    joins. (A v1 client can't read the v2 frame either, so it ends there too.)"""
    with disposable_project(expedition_files(), scaffold=False) as root:
        world = World(root)

    async def run(server: Server, players: Any) -> None:
        port = await server.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port, limit=wire.MAX_BYTES)
            try:
                writer.write(V1_JOIN)
                assert await wire.read(reader) == REFUSED
                assert await asyncio.wait_for(reader.read(1), 2) == b""
            finally:
                writer.close()
                await writer.wait_closed()
            assert not server.peers and not players()
        finally:
            await server.close()

    asyncio.run(run(Server(coop), lambda: coop.players))
    asyncio.run(run(WorldServer(world), lambda: world.members))


def test_a_v1_server_is_refused_by_a_v2_client() -> None:
    """The client joins with v2 only. A server answering with a v1 frame (welcome or refusal) is refused for its
    version; a v1 server, which closes on a v2 join, just ends the connection: the client never tries v1."""
    joins: list[wire.Message] = []

    def serve(answer: bytes | None) -> Any:
        async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            joins.append(await wire.read(reader))
            if answer is not None:
                writer.write(answer)
                await writer.drain()
            writer.close()
        return handle

    async def run(answer: bytes | None) -> None:
        listener = await asyncio.start_server(serve(answer), "127.0.0.1", 0)
        try:
            await connect(listener.sockets[0].getsockname()[1]).__aenter__()
        finally:
            listener.close()
            await listener.wait_closed()

    async def real_welcome() -> wire.Message:
        """A v2 server's own welcome (mesh_net.server), to turn into the v1 one a v1 server would send."""
        server = Server()
        port = await server.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port, limit=wire.MAX_BYTES)
            try:
                writer.write(wire.encode({"v": 2, "type": "join", "resume": None}))
                return await wire.read(reader)
            finally:
                writer.close()
                await writer.wait_closed()
        finally:
            await server.close()

    hello = asyncio.run(real_welcome())
    v1_welcome = wire.encode({**hello, "v": 1, "state": {**hello["state"], "v": 1}})
    for answer in (v1_welcome, b'{"v":1,"type":"refused","code":"capacity"}\n'):
        with pytest.raises(wire.VersionMismatch, match="protocol version 1"):
            asyncio.run(run(answer))
    with pytest.raises(EOFError):
        asyncio.run(run(None))
    assert [j["v"] for j in joins] == [2, 2, 2], "one v2 join each time, never a v1 retry"
    with pytest.raises(wire.VersionMismatch):  # N7's welcome
        check_welcome({**welcome("0" * 32, 1, "a" * 64, "w"), "v": 1}, "w")


def test_nan_and_infinity_never_pass_the_wire() -> None:
    async def read(data: bytes) -> wire.Message:
        reader = asyncio.StreamReader()
        reader.feed_data(data)
        return await wire.read(reader)

    for token in (b"NaN", b"Infinity", b"-Infinity"):
        with pytest.raises(wire.Invalid):
            asyncio.run(read(b'{"v":2,"type":"x","n":' + token + b"}\n"))
    assert asyncio.run(read(b'{"v":2,"type":"x","n":1e3}\n'))["n"] == 1000.0
    with pytest.raises(ValueError):  # (and nothing sends one)
        wire.encode({"v": 2, "n": float("nan")})


def test_a_2d_rooms_rows_carry_no_elevation_and_no_floor(coop: SceneRoom) -> None:
    room = coop
    a = room.join()
    try:
        state = room.snapshot()
        assert [r[4:] for r in state["players"]] == [[0, None]]
        check_state(state, room.identity, room)
        own = state["players"][0]
        for bad in ([*own[:4], 5.0, None], [*own[:4], 0, "ground"], [*own[:4], 0]):
            with pytest.raises(wire.Invalid):
                check_state({**state, "players": [bad]}, room.identity, room)
    finally:
        room.leave(a)


def test_an_older_snapshot_never_replaces_a_newer_one(coop: SceneRoom) -> None:
    """N6's client: a state whose tick is not newer than the last applied is refused (the connection ends) and the
    client keeps the newer. (N7's: test_mesh_net_world.test_the_client_applies_only_its_own_rooms_frames_in_order.)"""
    room = coop
    a = room.join()
    try:
        room.step()
        first = room.snapshot()
        room.step()
        second = room.snapshot()

        async def run() -> Client:
            reader = asyncio.StreamReader()
            client = Client(reader, None, a, "0" * 32, "a" * 64, first,  # type: ignore[arg-type]  # (receives only)
                            check=lambda s: check_state(s, room.identity, room))
            room.step()
            bad = {**room.snapshot(), "players": [[*r[:5], "ground"] for r in second["players"]]}  # newer, a floor
            reader.feed_data(wire.encode(second) + wire.encode(first) + wire.encode(second) + wire.encode(bad))
            assert await client.receive() == second
            for _ in range(2):  # the older one, then the same tick again
                with pytest.raises(wire.Invalid, match="out of order"):
                    await client.receive()
                assert client.state == second
            with pytest.raises(wire.Invalid, match="carries an elevation or a floor"):  # (checked before applied)
                await client.receive()
            assert client.state == second
            return client

        asyncio.run(run())
    finally:
        room.leave(a)
