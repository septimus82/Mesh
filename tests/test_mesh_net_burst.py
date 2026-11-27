"""Bursts of inputs (M4-1): a network or server stall holds a client's inputs back and they then arrive together. The
session must survive the burst a stall of 2 s builds up, in N6's Server and N7's WorldServer alike, while a sustained
flood is still refused with its reason (mesh_net.server.InputBudget). The old rule ended any session that sent more
than 8 frames within one tick, which a 400 ms network stall or a 600 ms server stall at 20 Hz already did."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import Counter
from typing import Any

import pytest

from mesh_net import protocol as wire
from mesh_net.client import connect
from mesh_net.scene_room import disposable_project
from mesh_net.server import InputBudget, Server, WorldServer
from mesh_net.world import World, expedition_files


def budget(clock: list[float]) -> InputBudget:
    async def make() -> InputBudget:
        return InputBudget()

    made = asyncio.run(make())
    made.clock, made.at = (lambda: clock[0]), clock[0]
    return made


@pytest.mark.fast
def test_the_budget_takes_a_stalls_backlog_and_refuses_a_flood():
    """The numbers, on a fake clock: a client keeping to HZ is never refused, nor the backlog of a 2.9 s stall; a new
    session may send 8 frames at once (the old limit); a sustained 3 x HZ is refused within BURST / HZ s."""
    clock = [0.0]
    fresh = budget(clock)
    assert all(fresh.take() for _ in range(8)) and not fresh.take()

    steady = budget(clock)
    for stall in (0.0, 1.0, 2.0, 2.9, 0.4):
        for _ in range(10 * wire.HZ):  # ten seconds at HZ
            clock[0] += 1 / wire.HZ
            assert steady.take()
        clock[0] += stall  # nothing arrives during the stall, then its whole backlog at once
        assert all(steady.take() for _ in range(round(stall * wire.HZ) + 1)), stall

    flood, sent, start = budget(clock), 0, clock[0]
    clock[0] += 10  # a full bucket, then three frames a tick
    while flood.take():
        clock[0] += 1 / (3 * wire.HZ)
        sent += 1
    assert clock[0] - start - 10 <= InputBudget.BURST / wire.HZ + 0.1 and sent > InputBudget.BURST


@pytest.mark.fast
def test_the_servers_own_stall_is_never_held_against_a_session():
    """#727, on a fake clock: the backlog of a 4 s stall is more than a full bucket. Refused when nothing says the
    server was held up (a client that went quiet, then floods); taken in full when the server's own loop was held
    up for it (``held``); and a sustained flood after it is still refused."""
    def backlog_fits(stalled: float) -> bool:
        clock, held = [0.0], [0.0]
        steady = budget(clock)
        steady.held = lambda: held[0]
        for _ in range(10 * wire.HZ):
            clock[0] += 1 / wire.HZ
            assert steady.take()
        clock[0] += 4.0
        held[0] += stalled
        fits = all(steady.take() for _ in range(4 * wire.HZ + 1))
        sent = 0
        while steady.take():  # then five frames a tick: refused within seconds, as ever
            clock[0] += 1 / (5 * wire.HZ)
            sent += 1
        assert sent < 10 * wire.HZ
        return fits

    assert not backlog_fits(0.0)
    assert backlog_fits(4.0 - 1 / wire.HZ)  # (Server.held counts what is beyond a tick)


@pytest.mark.fast
@pytest.mark.parametrize("stall", [4.0, 30.0, 3600.0])
def test_a_stalls_credit_is_bounded_and_drains_away(stall: float):
    """#727 review: a session quiet through a stall (one frame after it) cannot bank the credit. At once it may send at
    most BURST + CREDIT, however long the stall; a few seconds on, no more than BURST, as ever. Nor do ten stalls in a
    row, or an hour of a slow server's lateness (40% of each tick), add up to more."""
    clock, held = [0.0], [0.0]
    quiet = budget(clock)
    quiet.held = lambda: held[0]
    for _ in range(10 * wire.HZ):
        clock[0] += 1 / wire.HZ
        assert quiet.take()

    def bounded() -> None:
        """At once at most BURST + CREDIT; after three quiet seconds, at most BURST."""
        assert quiet.tokens <= InputBudget.BURST + InputBudget.CREDIT, quiet.tokens
        clock[0] += 3.0
        burst = 0
        while quiet.take():
            burst += 1
        assert burst <= InputBudget.BURST, burst
        clock[0] += 10  # (a full bucket again)

    clock[0] += stall
    held[0] += stall - 1 / wire.HZ
    assert quiet.take()
    bounded()
    for _ in range(10):  # ten 30 s stalls in a row, one frame after each
        clock[0] += 30
        held[0] += 30 - 1 / wire.HZ
        assert quiet.take()
    bounded()
    for _ in range(360):  # an hour of a server late by 40% of each second, one frame every 10 s
        clock[0] += 10
        held[0] += 4
        assert quiet.take()
    bounded()


@pytest.mark.fast
def test_the_clock_never_bursts_a_stalls_missed_ticks(monkeypatch: pytest.MonkeyPatch):
    """Server._next_tick on a fake clock: after a 2 s stall the next tick comes at once (the late one) and every tick
    after it 1/HZ later, never a run of the missed ones; and the stall is counted in ``stalled`` once."""
    import mesh_net.server

    clock = [0.0]

    class Loop:
        def time(self) -> float:
            return clock[0]

    async def sleep(delay: float) -> None:
        clock[0] += max(0.0, delay)

    monkeypatch.setattr(mesh_net.server.asyncio, "sleep", sleep)
    server, loop = Server(), Loop()

    def tick() -> float:
        before, step = clock[0], server._next_tick(loop)
        with pytest.raises(StopIteration):
            step.send(None)
        return clock[0] - before

    assert all(tick() == pytest.approx(1 / wire.HZ) for _ in range(10))
    clock[0] += 2.0
    tick()
    counted = server.stalled
    assert counted == pytest.approx(2.0 - 2 / wire.HZ)
    waits = [tick() for _ in range(20)]
    assert sum(w < 1e-9 for w in waits) <= 1 and waits[1:] == pytest.approx([1 / wire.HZ] * 19), waits
    assert server.stalled == counted


# --- over sockets: N6 Server and N7 WorldServer -----------------------------------------------------------------


def n7_world() -> World:
    with disposable_project(expedition_files(), scaffold=False) as root:
        return World(root)


class Session:
    """A bare socket session with either server: joins, then sends input frames of its own (room and entity from the
    welcome, or N7's enter frame) while a task reads every frame that comes, until the server closes the session."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, frame: wire.Message, sid: int):
        self.writer, self.frame, self.id, self.seq, self.received = writer, frame, sid, 0, 0
        self.reading = asyncio.create_task(self._read(reader))

    @classmethod
    async def open(cls, port: int) -> Session:
        reader, writer = await asyncio.open_connection("127.0.0.1", port, limit=wire.MAX_BYTES)
        writer.write(wire.encode({"v": wire.VERSION, "type": "join", "resume": None}))
        hello = await wire.read(reader)
        frame: wire.Message = {"v": wire.VERSION, "type": "input", "tick": 0, "entity": hello.get("entity")}
        while frame["entity"] is None:  # N7: the player's room and avatar come in its enter frame
            msg = await asyncio.wait_for(wire.read(reader), 3)
            if msg["type"] == "enter":
                frame.update(room=msg["room"], entity=msg["entity"])
        return cls(reader, writer, frame, hello.get("player", hello.get("entity")))

    async def _read(self, reader: asyncio.StreamReader) -> None:
        try:
            while True:
                await wire.read(reader)
                self.received += 1
        except (EOFError, OSError, wire.Invalid):
            pass  # the server closed the session

    def send(self, n: int) -> None:
        data = b""
        for _ in range(n):
            self.seq += 1
            data += wire.encode({**self.frame, "seq": self.seq, "dx": 1, "dy": 0})
        self.writer.write(data)

    async def steady(self, ticks: int) -> None:
        """Send one input a tick, as a client does."""
        for _ in range(ticks):
            self.send(1)
            await asyncio.sleep(1 / wire.HZ)

    async def close(self) -> None:
        self.reading.cancel()
        self.writer.close()
        try:
            await asyncio.wait_for(self.writer.wait_closed(), 2)
        except (OSError, TimeoutError):
            self.writer.transport.abort()


def host(kind: str) -> tuple[Server, Any]:
    """The server, and the object whose ``input`` takes each accepted input frame."""
    if kind == "N6":
        server = Server()
        return server, server.room
    world = n7_world()
    return WorldServer(world), world


def record_ticks(target: Any) -> Counter[int]:
    """Count the input frames the server hands on, by tick: the proof a burst really arrived within one tick."""
    ticks: Counter[int] = Counter()
    original = target.input

    def recording(*args: Any) -> None:
        ticks[target.tick] += 1
        original(*args)

    target.input = recording
    return ticks


@pytest.mark.integration
@pytest.mark.parametrize("stall", [1, 2])
@pytest.mark.parametrize("kind", ["N6", "N7"])
def test_the_backlog_of_a_stall_arrives_at_once_and_the_session_stays(kind: str, stall: int):
    """(a) A client connected for a while is held back for a stall, then everything held back arrives in one write
    (stall x HZ inputs, plus the one in flight), as TCP delivers it after a retransmission; the server takes them all
    within a tick and keeps the session."""
    async def run() -> None:
        server, target = host(kind)
        port = await server.start()
        try:
            session = await Session.open(port)
            try:
                await session.steady(30)
                ticks = record_ticks(target)
                await asyncio.sleep(stall)  # the stall: nothing gets through ...
                session.send(stall * wire.HZ + 1)  # ... then everything held back arrives at once
                await session.writer.drain()
                received = session.received
                await session.steady(10)
                assert not session.reading.done() and session.id in server.peers, "the burst ended the session"
                assert session.received > received
                assert sum(ticks.values()) >= stall * wire.HZ + 1 and max(ticks.values()) > 8, ticks
            finally:
                await session.close()
        finally:
            await server.close()

    asyncio.run(run())


@pytest.mark.integration
def test_a_server_stall_with_a_real_20hz_client_keeps_the_session():
    """(b) The server's event loop blocks for 1 s (GC, a store write, a debugger) while a real client keeps sending at
    HZ on its own loop; the stall's backlog is then read within one tick, and the client stays connected. No timing
    is asserted: the proof the burst happened is the per-tick count the server saw."""
    ready, held = threading.Event(), {}

    def serve() -> None:
        loop = asyncio.new_event_loop()
        server = Server()
        held.update(loop=loop, server=server, ticks=record_ticks(server.room), port=loop.run_until_complete(server.start()))
        ready.set()
        try:
            loop.run_forever()
        finally:
            loop.run_until_complete(server.close())
            loop.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    assert ready.wait(10)
    loop, server = held["loop"], held["server"]

    async def client() -> None:
        async with connect(held["port"]) as c:
            async def send() -> None:
                clock = asyncio.get_running_loop()
                due = clock.time()
                while True:
                    await c.input(1, 0)
                    due = max(due + 1 / wire.HZ, clock.time())
                    await asyncio.sleep(due - clock.time())

            sending = asyncio.create_task(send())
            try:
                for _ in range(20):
                    await c.receive()
                loop.call_soon_threadsafe(time.sleep, 1.0)  # the server's loop blocks for a second
                for _ in range(20):
                    await asyncio.wait_for(c.receive(), 5)
                assert c.entity in server.peers
            finally:
                sending.cancel()

    try:
        asyncio.run(client())
        assert max(held["ticks"].values()) > 8, held["ticks"]  # the stall's backlog arrived within one tick
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(10)
    assert not thread.is_alive()


@pytest.mark.integration
@pytest.mark.parametrize(("kind", "where"), [("N7", "step"), ("N6", "loop")])
def test_a_server_stall_longer_than_the_bucket_never_ends_a_session(kind: str, where: str):
    """(d) #727: the server's loop is held up for 4 s, longer than BURST / HZ (3 s) and shorter than a client's 5 s
    read timeout: inside a step, as a store commit slow to reach the disk holds it (N7, the hosted Windows failure),
    or by anything else on the loop (N6). Two clients on their own loop keep to HZ throughout, so the backlog is more
    than a full bucket; both sessions stay, because the server's own stall is never held against them."""
    stall, ready, held = 4.0, threading.Event(), {}
    armed = threading.Event()

    def serve() -> None:
        loop = asyncio.new_event_loop()
        server, target = host(kind)
        original = target.step

        def step() -> None:
            original()
            if armed.is_set():
                armed.clear()
                time.sleep(stall)

        target.step = step
        held.update(loop=loop, server=server, port=loop.run_until_complete(server.start()))
        ready.set()
        try:
            loop.run_forever()
        finally:
            loop.run_until_complete(server.close())
            loop.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    assert ready.wait(20)
    loop, server = held["loop"], held["server"]

    async def keep_to_hz(session: Session) -> None:
        clock = asyncio.get_running_loop()
        due = clock.time()
        while True:
            session.send(1)
            due = max(due + 1 / wire.HZ, clock.time())
            await asyncio.sleep(due - clock.time())

    async def clients() -> None:
        sessions = [await Session.open(held["port"]) for _ in range(2)]
        sending = [asyncio.create_task(keep_to_hz(s)) for s in sessions]
        try:
            await asyncio.sleep(1)
            if where == "step":
                armed.set()
            else:
                loop.call_soon_threadsafe(time.sleep, stall)
            await asyncio.sleep(stall + 0.5)
            received = [s.received for s in sessions]
            await asyncio.sleep(1)
            for session, before in zip(sessions, received):
                assert not session.reading.done() and session.id in server.peers, "the server's stall ended a session"
                assert session.received > before
        finally:
            for task in sending:
                task.cancel()
            for session in sessions:
                await session.close()

    try:
        asyncio.run(clients())
        assert server.stalled > InputBudget.BURST / wire.HZ, server.stalled  # (the stall outlasted a full bucket)
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(10)
    assert not thread.is_alive()


@pytest.mark.integration
@pytest.mark.parametrize("kind", ["N6", "N7"])
def test_a_sustained_flood_is_still_refused_with_its_reason(kind: str, caplog: pytest.LogCaptureFixture):
    """(c) A client connected for a while then sends five inputs a tick (2.5 x the bucket's refill, 5 x a client's
    rate): the server closes the session and logs why."""
    caplog.set_level(logging.INFO, logger="mesh_net.server")

    async def run() -> None:
        server, _ = host(kind)
        port = await server.start()
        try:
            session = await Session.open(port)
            try:
                await session.steady(30)
                for _ in range(10 * wire.HZ):  # at most 10 s of flooding
                    session.send(5)
                    await asyncio.sleep(1 / wire.HZ)
                    if session.reading.done():
                        break
                assert session.reading.done(), "a flood was never refused"
                assert session.id not in server.peers
            finally:
                await session.close()
        finally:
            await server.close()

    asyncio.run(run())
    reason = "input rate" if kind == "N6" else "request rate"
    assert f"[Mesh][Net] session closed: {reason}" in caplog.messages
