"""Wire protocol v3 (owner decision OD2, M4-2): a peer of another version (v2, v1) is refused at the handshake with a
reason, in either direction and on both servers, with no downgrade; JSON's NaN and Infinity never reach a check; a 2D
room's rows carry elevation 0 and no floor; v3's additions (acknowledgements, attack and hit counters, enemy
placement, intended and view ticks, the welcome's tick rate) are checked exactly, and a malformed, stale or
inconsistent frame is refused whole, before anything of it is applied. (The HD-2D rows: tests/test_mesh_net_hd2d.py;
combat presentation: tests/test_mesh_net_combat.py.)"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from mesh_net import protocol as wire
from mesh_net.client import Client, connect
from mesh_net.persistence import check_character
from mesh_net.scene_room import (
    COOP_SCENE,
    Feedback,
    SceneRoom,
    check_progress,
    check_state,
    coop_files,
    disposable_project,
    parse_input,
)
from mesh_net.server import Server, WorldServer
from mesh_net.world import World, check_frame, check_welcome, expedition_files, welcome

pytestmark = pytest.mark.integration  # (sockets, rooms built in folders)

OLD_JOINS = {2: b'{"v":2,"type":"join","resume":null}\n', 1: b'{"v":1,"type":"join","resume":null}\n'}
REFUSED = {"v": wire.VERSION, "type": "refused", "code": "protocol_version"}
BANDIT = "start_bandit_608_256_0_0"


@pytest.fixture(scope="module")
def coop() -> SceneRoom:
    with disposable_project(coop_files(), scaffold=False) as root:
        return SceneRoom(root / COOP_SCENE, root)


@pytest.fixture(scope="module")
def world() -> World:
    with disposable_project(expedition_files(), scaffold=False) as root:
        return World(root)


@pytest.mark.parametrize("version", [2, 1, 4, 0, "3", 3.0, True, None])
def test_every_frame_of_another_version_is_refused_as_such(version: Any) -> None:
    msg = {"v": version, "type": "join", "resume": None}
    with pytest.raises(wire.VersionMismatch, match="speaks version 3 only"):
        wire.fields(msg, "join", "resume")
    wire.fields({**msg, "v": wire.VERSION}, "join", "resume")
    assert wire.VERSION == 3


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
        wire.fields({"v": 2, "type": "welcome"}, "welcome")
    except wire.VersionMismatch as exc:
        mismatch = exc
    assert mismatch is not None and reason(mismatch) == "protocol version 2: this Mesh speaks version 3 only"
    assert reason(wire.Invalid("refused (protocol_version)")) == "refused (protocol_version)"
    assert reason(asyncio.IncompleteReadError(b"", None)) == "IncompleteReadError"
    assert len(reason(wire.Invalid("x" * 500))) == 64


@pytest.mark.parametrize("old", [2, 1])
def test_an_old_client_is_refused_by_both_v3_servers_with_a_reason(old: int, coop: SceneRoom, world: World) -> None:
    """N6 and N7: a v2 (or v1) join is answered with ``refused`` (code protocol_version) and the connection closed;
    nobody joins. (An old client can't read the v3 frame either, so it ends there too.)"""

    async def run(server: Server, players: Any) -> None:
        port = await server.start()
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port, limit=wire.MAX_BYTES)
            try:
                writer.write(OLD_JOINS[old])
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


def serve(answer: bytes | None, joins: list[wire.Message]) -> Any:
    """A fake server: records the join, answers ``answer`` (or nothing), closes."""
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        joins.append(await wire.read(reader))
        if answer is not None:
            writer.write(answer)
            await writer.drain()
        writer.close()
    return handle


async def join_fake(answer: bytes | None, joins: list[wire.Message], **checks: Any) -> None:
    listener = await asyncio.start_server(serve(answer, joins), "127.0.0.1", 0)
    try:
        await connect(listener.sockets[0].getsockname()[1], **checks).__aenter__()
    finally:
        listener.close()
        await listener.wait_closed()


async def real_welcome(room: Any = None) -> wire.Message:
    """A v3 server's own welcome (mesh_net.server)."""
    server = Server(room)
    port = await server.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port, limit=wire.MAX_BYTES)
        try:
            writer.write(wire.encode({"v": wire.VERSION, "type": "join", "resume": None}))
            return await wire.read(reader)
        finally:
            writer.close()
            await writer.wait_closed()
    finally:
        await server.close()


def test_an_old_server_is_refused_by_a_v3_client(world: World) -> None:
    """The client joins with v3 only. A server answering with a v2 frame (welcome or refusal, as a v2 server refuses
    a v3 join) is refused for its version; one that closes just ends the connection: the client never retries older.
    The N7 welcome, enter, room_state and N8 character frames are refused at v2 too."""
    joins: list[wire.Message] = []
    hello = asyncio.run(real_welcome())
    assert hello["hz"] == wire.HZ
    v2_welcome = {k: v for k, v in hello.items() if k != "hz"}
    v2_welcome = wire.encode({**v2_welcome, "v": 2, "state": {**hello["state"], "v": 2}})
    for answer in (v2_welcome, b'{"v":2,"type":"refused","code":"protocol_version"}\n'):
        with pytest.raises(wire.VersionMismatch, match="protocol version 2"):
            asyncio.run(join_fake(answer, joins))
    with pytest.raises(EOFError):
        asyncio.run(join_fake(None, joins))
    assert [j["v"] for j in joins] == [3, 3, 3], "one v3 join each time, never an older retry"

    with pytest.raises(wire.VersionMismatch):
        check_welcome({**welcome("0" * 32, 1, "a" * 64, world.identity), "v": 2}, world.identity)
    ids = {k: d.proto.identity for k, d in world.defs.items()}
    hub = world._create(world.start, None)
    eid = hub.room.join()
    state = hub.room.snapshot()
    enter = {"v": wire.VERSION, "type": "enter", "room": hub.id, "key": hub.key, "entity": eid, "state": state}
    room_state = {"v": wire.VERSION, "type": "room_state", "room": hub.id, "state": state}
    character = {"v": wire.VERSION, "type": "character", "id": "a" * 32, "name": "Ada", "items": [], "unlocks": [],
                 "completed": 0, "loot": []}
    check_frame(enter, ids)
    check_frame(room_state, ids)
    check_character(character)
    for frame in (enter, room_state, character):
        with pytest.raises(wire.VersionMismatch):
            check_frame({**frame, "v": 2}, ids)
    for frame in (enter, room_state):  # (a v2 state inside a v3 frame: refused too)
        with pytest.raises(wire.VersionMismatch):
            check_frame({**frame, "state": {**state, "v": 2}}, ids)


def test_a_welcome_must_carry_this_sides_tick_rate(coop: SceneRoom, world: World) -> None:
    """``hz`` is in both welcomes; a server ticking at another rate (or none said) is refused: both sides' timing is
    built on HZ."""
    hello = asyncio.run(real_welcome(coop))
    assert hello["hz"] == wire.HZ
    joins: list[wire.Message] = []
    checks = {"check": lambda s: check_state(s, coop.identity, coop), "check_input": parse_input}
    without = {k: v for k, v in hello.items() if k != "hz"}
    for bad in ({**hello, "hz": 30}, {**hello, "hz": 20.0}, {**hello, "hz": "20"}, without):
        with pytest.raises(wire.Invalid):
            asyncio.run(join_fake(wire.encode(bad), joins, **checks))
    good = welcome("0" * 32, 1, "a" * 64, world.identity)
    check_welcome(good, world.identity)
    for bad in ({**good, "hz": 10}, {k: v for k, v in good.items() if k != "hz"}):
        with pytest.raises(wire.Invalid):
            check_welcome(bad, world.identity)


def test_input_frames_carry_an_intended_tick_and_an_attacks_view_tick() -> None:
    """Every input names the tick it is meant for (OD11); only an attack may name the tick its window showed (reserved
    for lag compensation, M4-5). Anything else about them is refused."""
    good = wire.input_frame(3, 1, 1, 0, 7)
    assert good == {"v": wire.VERSION, "type": "input", "entity": 3, "seq": 1, "tick": 7, "dx": 1, "dy": 0}
    attack = wire.input_frame(3, 2, 0, 0, 8, "attack", view_tick=5.5)
    for frame in (good, attack, wire.input_frame(3, 2, 0, 0, 0, "attack", view_tick=0)):
        parse_input(frame, 3)
        wire.movement(frame, 3)
    bad = [{k: v for k, v in good.items() if k != "tick"}, {**good, "tick": -1}, {**good, "tick": 1.0},
           {**good, "tick": True}, {**good, "tick": None}, {**good, "tick": "7"}, {**good, "tick": wire.MAX_SEQ + 1},
           {**good, "view_tick": 5.0}, wire.input_frame(3, 2, 0, 0, 8, "use", view_tick=5.0),
           {**attack, "view_tick": float("nan")}, {**attack, "view_tick": -0.5}, {**attack, "view_tick": True},
           {**attack, "view_tick": "5"}, {**attack, "view_tick": wire.MAX_SEQ + 1.0}, {**attack, "view_tick": None}]
    for frame in bad:
        with pytest.raises(wire.Invalid):
            parse_input(frame, 3)
        with pytest.raises(wire.Invalid):
            wire.movement(frame, 3)


def test_nan_and_infinity_never_pass_the_wire() -> None:
    async def read(data: bytes) -> wire.Message:
        reader = asyncio.StreamReader()
        reader.feed_data(data)
        return await wire.read(reader)

    for token in (b"NaN", b"Infinity", b"-Infinity"):
        with pytest.raises(wire.Invalid):
            asyncio.run(read(b'{"v":3,"type":"x","n":' + token + b"}\n"))
    assert asyncio.run(read(b'{"v":3,"type":"x","n":1e3}\n'))["n"] == 1000.0
    with pytest.raises(ValueError):  # (and nothing sends one)
        wire.encode({"v": wire.VERSION, "n": float("nan")})


def test_a_2d_rooms_rows_carry_no_elevation_and_no_floor(coop: SceneRoom) -> None:
    room = coop
    a = room.join()
    try:
        state = room.snapshot()
        assert [r[4:6] for r in state["players"]] == [[0, None]]
        assert [r[5:] for r in state["enemies"]] == [[0, None]]
        check_state(state, room.identity, room)
        own, enemy = state["players"][0], state["enemies"][0]
        for bad in ([*own[:4], 5.0, None, 0, 0], [*own[:4], 0, "ground", 0, 0], [*own[:4], 0, None, 0]):
            with pytest.raises(wire.Invalid):
                check_state({**state, "players": [bad]}, room.identity, room)
        for bad_enemy in ([*enemy[:5], 5.0, None], [*enemy[:5], 0, "ground"]):
            with pytest.raises(wire.Invalid, match="enemy row carries an elevation or a floor"):
                check_state({**state, "enemies": [bad_enemy]}, room.identity, room)
    finally:
        room.leave(a)


def test_malformed_v3_rows_are_refused(coop: SceneRoom) -> None:
    """A player row is [entity, x, y, facing, elevation, floor, ack, attack_seq]; an enemy row is [id, hp, hit_seq, x,
    y, elevation, floor]. Wrong arity, types, negative or non-integer counters, an enemy the room doesn't have or named
    twice: refused (wire.Invalid)."""
    room = coop
    a = room.join()
    try:
        room.step()
        state = room.snapshot()
        check_state(state, room.identity, room)
        own, enemy = state["players"][0], state["enemies"][0]
        bad_players = [own[:6], own[:7], [*own, 0], [*own[:6], -1, 0], [*own[:6], 0, -1], [*own[:6], 1.0, 0],
                       [*own[:6], 0, 1.5], [*own[:6], True, 0], [*own[:6], 0, None], [*own[:6], "1", 0],
                       [*own[:6], wire.MAX_SEQ + 1, 0]]
        for bad in bad_players:
            with pytest.raises(wire.Invalid, match="invalid player row"):
                check_state({**state, "players": [bad]})
        bad_enemies = [[enemy[:2]], [enemy[:6]], [[*enemy, None]], [[enemy[0], enemy[1], -1, *enemy[3:]]],
                       [[enemy[0], enemy[1], 0.5, *enemy[3:]]], [[enemy[0], enemy[1], True, *enemy[3:]]],
                       [[enemy[0], -1.0, *enemy[2:]]], [[enemy[0], True, *enemy[2:]]], [[3, *enemy[1:]]],
                       [[*enemy[:3], float("nan"), *enemy[4:]]], [[*enemy[:5], 100_001.0, None]],
                       [[*enemy[:6], ""]], [[*enemy[:6], 7]], [enemy, enemy]]
        for bad in bad_enemies:
            with pytest.raises(wire.Invalid, match="invalid enemies"):
                check_state({**state, "enemies": bad})
        with pytest.raises(wire.Invalid, match="enemy this room does not have"):
            check_state({**state, "enemies": [["nobody", *enemy[1:]]]}, room.identity, room)
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
                            check=lambda s: check_state(s, room.identity, room), progress=check_progress)
            room.step()
            bad = {**room.snapshot(), "players": [[*r[:5], "ground", *r[6:]] for r in second["players"]]}  # a floor
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


def stale_variants(state: wire.Message, own: int) -> list[tuple[str, wire.Message]]:
    """Newer (by tick), well-formed states that are stale or inconsistent with ``state`` (own entity ``own``)."""
    def players(change: Any) -> wire.Message:
        return {**state, "tick": state["tick"] + 1, "players": [change(r) for r in state["players"]]}

    enemies = [[r[0], r[1], r[2] - 1, *r[3:]] for r in state["enemies"]]
    return [("an input this client never sent", players(lambda r: [*r[:6], 99, r[7]] if r[0] == own else r)),
            ("acknowledgement or attack count went back", players(lambda r: [*r[:6], r[6] - 1, r[7]])),
            ("acknowledgement or attack count went back", players(lambda r: [*r[:7], r[7] - 1])),
            ("hit count went back", {**state, "tick": state["tick"] + 1, "enemies": enemies})]


def test_stale_or_inconsistent_counters_are_refused_whole(coop: SceneRoom, world: World) -> None:
    """Within a room instance no acknowledgement, attack count or hit count goes back, and a client's own ack never
    names a seq it hasn't sent (check_progress): N6's client and N7's refuse such a state (the session ends) and keep
    what they had, nothing of it applied."""
    from mesh_net.world_client import WorldArena

    room = coop
    a = room.join()
    try:
        room.enemies[BANDIT].hit_seq = 2  # (as if hit twice)
        for seq in (1, 2, 3):
            room.input(a, wire.input_frame(a, seq, 0, 0, room.tick + 1, "attack" if seq == 1 else None))
            room.step()
        state = room.snapshot()
        own = next(r for r in state["players"] if r[0] == a)
        assert (own[6], own[7], state["enemies"][0][2]) == (3, 1, 2)
        check_progress(state, {**state, "tick": state["tick"] + 1}, a, 3)
        for why, bad in stale_variants(state, a):
            with pytest.raises(wire.Invalid, match=why):
                check_progress(state, bad, a, 3)

            async def n6(bad: wire.Message = bad) -> None:
                reader = asyncio.StreamReader()
                client = Client(reader, None, a, "0" * 32, "a" * 64, state, 3,  # type: ignore[arg-type]
                                check=lambda s: check_state(s, room.identity, room), progress=check_progress)
                reader.feed_data(wire.encode(bad))
                with pytest.raises(wire.Invalid, match=why):
                    await client.receive()
                assert client.state is state

            asyncio.run(n6())
    finally:
        room.leave(a)
        room.enemies[BANDIT].hit_seq = 0

    hub = world._create(world.start, None)
    eid = hub.room.join()
    hub.room.input(eid, wire.input_frame(eid, 1, 0, 0, 1, "attack"))
    hub.room.step()
    state = hub.room.snapshot()
    ids = {k: d.proto.identity for k, d in world.defs.items()}
    for why, bad in stale_variants(state, eid)[1:3]:  # (the players' counters; an ack beyond what was sent: below)
        arena: Any = SimpleNamespace(identities=ids, defs=world.defs, room=None, key=None, entity=None, state=None,
                                     playback=None, pending=None, phase="loading", feedback=Feedback(), seq=1,
                                     actions=[], view=None, shown=None)
        WorldArena.on_frame(arena, {"v": wire.VERSION, "type": "enter", "room": hub.id, "key": hub.key, "entity": eid,
                                    "state": state}, 0.0)
        kept, kept_playback = arena.state, list(arena.playback.states)
        with pytest.raises(wire.Invalid, match=why):
            WorldArena.on_frame(arena, {"v": wire.VERSION, "type": "room_state", "room": hub.id, "state": bad}, 0.1)
        assert arena.state is kept and list(arena.playback.states) == kept_playback, "nothing of it applied"
    arena.seq = 0  # (this window has sent nothing in this room... yet the server acknowledges seq 1)
    with pytest.raises(wire.Invalid, match="never sent"):
        WorldArena.on_frame(arena, {"v": wire.VERSION, "type": "room_state", "room": hub.id,
                                    "state": {**state, "tick": state["tick"] + 1}}, 0.1)
    assert arena.state is kept


def test_a_resumed_scene_session_passes_its_own_checks(coop: SceneRoom) -> None:
    """N6 through the real Server with the scene client's own checks (check_state against its room, check_progress):
    a session that sent inputs and attacks (its ack and attack count above 0) drops and resumes; the resumed one
    starts counting anew (SceneRoom.leave: per room join), so its first states pass check_progress against the new
    client's own seq, and it plays on."""
    room = coop
    room.locked.clear()

    async def run() -> None:
        server = Server(room)
        port = await server.start()
        checks = {"check": lambda s: check_state(s, room.identity, room), "check_input": parse_input,
                  "progress": check_progress}
        try:
            async with connect(port, **checks) as client:
                for _ in range(12):
                    await client.input(1, 0, "attack", client.state["tick"])
                    await client.receive()
                own = next(r for r in client.state["players"] if r[0] == client.entity)
                assert own[6] > 0 and own[7] > 0, "acknowledged inputs and an attack before the drop"
                token = client.resume
            await asyncio.sleep(0.2)
            async with connect(port, token, **checks) as client:
                own = next(r for r in client.state["players"] if r[0] == client.entity)
                assert own[6:] == [0, 0], "a new room join counts anew"
                for _ in range(12):
                    await client.input(0, 1)
                    await client.receive()
        finally:
            await server.close()
            for eid in list(room.players):
                room.leave(eid)

    asyncio.run(run())


def test_a_resumed_world_player_counts_anew_in_its_room(world: World) -> None:
    """N7: a resume always arrives as an enter (a new baseline), and the window keeps one seq for its life, so its
    path differs from N6's; the room still counts the resumed player anew (leave: per room join), and a window that
    has sent nothing yet (seq 0) accepts the states that follow."""
    from mesh_net.world_client import WorldArena

    pid, token = world.connect(None)
    m = world.members[pid]
    inst = world.instances[m.instance]
    for seq in range(1, 6):
        world.input(pid, wire.input_frame(m.eid, seq, 0, 0, inst.room.tick, "attack" if seq == 1 else None,
                                          room=inst.id))
        world.step()
    own = next(r for r in inst.room.snapshot()["players"] if r[0] == m.eid)
    assert own[6] == 5 and own[7] == 1
    world.disconnect(pid)
    world.connect(token)
    (enter,) = [f for f in world.take(pid) if f["type"] == "enter"]
    assert [r[6:] for r in enter["state"]["players"] if r[0] == enter["entity"]] == [[0, 0]]
    ids = {k: d.proto.identity for k, d in world.defs.items()}
    arena: Any = SimpleNamespace(identities=ids, defs=world.defs, room=None, key=None, entity=None, state=None,
                                 playback=None, pending=None, phase="loading", feedback=Feedback(), seq=0, actions=[],
                                 view=None, shown=None)
    WorldArena.on_frame(arena, enter, 0.0)
    for _ in range(3):
        world.step()
        (state,) = [f for f in world.deliver()[pid] if f["type"] == "room_state"]
        WorldArena.on_frame(arena, state, 0.1)
    world.disconnect(pid)
