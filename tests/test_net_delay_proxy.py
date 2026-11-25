"""M4-6's TCP delay proxy (tooling/net_delay_proxy.py): each direction held by M4-0's link model, never reordered, over
real loopback sockets; seeded."""

from __future__ import annotations

import asyncio
import random
import time

import pytest

from tooling.net_delay_proxy import DelayProxy, Link

SLACK_MS = 60.0  # a loaded runner's scheduling (and Windows' 15.6 ms timer) on top of the model's delay: report-only


async def echo_server() -> tuple[asyncio.Server, int]:
    async def echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
        writer.close()  # (the client's end of stream reached here: end ours)

    server = await asyncio.start_server(echo, "127.0.0.1", 0)
    return server, int(server.sockets[0].getsockname()[1])


async def through(proxy: DelayProxy, talk: object) -> object:
    """``talk(reader, writer)`` against an echo server behind ``proxy``."""
    server, port = await echo_server()
    proxy.target = ("127.0.0.1", port)
    listen = await proxy.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", listen)
        try:
            return await asyncio.wait_for(talk(reader, writer), 20)  # type: ignore[operator]
        finally:
            writer.close()
    finally:
        await proxy.close()
        server.close()
        await server.wait_closed()


async def round_trips(reader: asyncio.StreamReader, writer: asyncio.StreamWriter, n: int, gap: float) -> list[float]:
    """``n`` 8-byte pings ``gap`` s apart; each one's echo time (ms), checking they come back whole and in order."""
    sent: list[float] = []

    async def send() -> None:
        for i in range(n):
            sent.append(time.perf_counter())
            writer.write(i.to_bytes(8, "big"))
            await writer.drain()
            await asyncio.sleep(gap)

    sender = asyncio.create_task(send())
    times = []
    for i in range(n):
        assert int.from_bytes(await reader.readexactly(8), "big") == i, "in order, whole"
        times.append((time.perf_counter() - sent[i]) * 1000)
    await sender
    return times


@pytest.mark.integration
def test_each_direction_holds_half_the_round_trip_within_its_jitter() -> None:
    proxy = DelayProxy(("127.0.0.1", 0), rtt_ms=100.0, jitter_ms=10.0, seed=7)
    times = asyncio.run(through(proxy, lambda r, w: round_trips(r, w, 30, 0.02)))
    assert isinstance(times, list)
    assert min(times) >= 100.0 - 2 * 10.0 - 1.0, f"never sooner than RTT less both jitters: {min(times):.1f} ms"
    assert max(times) <= 100.0 + 2 * 10.0 + SLACK_MS, f"no more than RTT and both jitters (+ slack): {max(times):.1f} ms"
    assert proxy.counts["up"].chunks >= 1 and proxy.counts["up"].held == 0, "jitter alone never counts as a stall"


@pytest.mark.integration
def test_jitter_never_reorders_a_stream_and_an_end_of_stream_follows_its_bytes() -> None:
    """Many writes far closer together than the jitter's spread: the stream arrives byte for byte; the client's end of
    stream reaches the server after its bytes, and the server's comes back after the echo."""
    payload = random.Random(1).randbytes(200_000)  # (every chunk different: a reordering shows)

    async def talk(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> bytes:
        for start in range(0, len(payload), 2000):
            writer.write(payload[start:start + 2000])
            await writer.drain()
            await asyncio.sleep(0.001)
        writer.write_eof()
        return await reader.read()  # (to the server's end of stream)

    proxy = DelayProxy(("127.0.0.1", 0), rtt_ms=40.0, jitter_ms=20.0, seed=3)
    assert asyncio.run(through(proxy, talk)) == payload
    assert proxy.counts["up"].chunks > 10 and proxy.counts["up"].bytes == proxy.counts["down"].bytes == len(payload)


@pytest.mark.integration
def test_a_loss_stalls_the_stream_by_a_retransmission() -> None:
    """With loss, a chunk waits RTT + rto more, as a retransmitted segment would (and is counted as held)."""
    proxy = DelayProxy(("127.0.0.1", 0), rtt_ms=20.0, loss=0.999, rto_ms=100.0, seed=1)
    times = asyncio.run(through(proxy, lambda r, w: round_trips(r, w, 3, 0.3)))
    assert isinstance(times, list)
    assert min(times) >= 2 * (10.0 + 20.0 + 100.0) - 1.0, f"both ways stalled: {min(times):.1f} ms"
    assert proxy.counts["up"].held == proxy.counts["up"].chunks >= 3
    assert all(ms >= 130.0 - 0.1 for ms in proxy.counts["up"].held_ms)


@pytest.mark.fast
def test_one_seed_one_run_and_the_probes_model() -> None:
    """Each connection's two links come from the seed, in arrival order; each is M4-0's Link (one way RTT/2 +- jitter,
    in order), so the proxy delays sockets as the probe models them."""
    def draws(seed: int) -> list[list[float]]:
        proxy = DelayProxy(("127.0.0.1", 1), rtt_ms=100.0, jitter_ms=10.0, loss=0.01, seed=seed)
        return [[link.arrival(i * 50.0) for i in range(100)] for link in (proxy.link() for _ in range(4))]

    a = draws(7)
    assert a == draws(7) and a != draws(8)
    assert len({tuple(d) for d in a}) == 4, "every link its own stream"
    delays = [t - i * 50.0 for i, t in enumerate(a[0])]
    assert all(t2 >= t1 for t1, t2 in zip(a[0], a[0][1:])), "in order"
    assert min(delays) >= 40.0 and len({round(d, 6) for d in delays}) > 50, "RTT/2 with jitter, varied"
    proxy = DelayProxy(("127.0.0.1", 1), rtt_ms=100.0, jitter_ms=10.0, loss=0.01, rto_ms=150.0)
    link = proxy.link()
    assert isinstance(link, Link) and (link.one_way_ms, link.jitter_ms, link.loss, link.rto_ms) == (50.0, 10.0, 0.01, 150.0)
    for bad in ({"rtt_ms": -1.0}, {"jitter_ms": -1.0}, {"loss": 1.0}, {"rto_ms": -5.0}):
        with pytest.raises(ValueError):
            DelayProxy(("127.0.0.1", 1), **bad)  # type: ignore[arg-type]


@pytest.mark.integration
def test_the_coop_server_and_two_clients_play_through_it() -> None:
    """The real co-op authority (mesh_net.server.Server) and two real clients (mesh_net.client.connect, as the windows
    connect) through the proxy at 100 ms: both join, see each other, and an input is acknowledged about a round trip
    later (never sooner)."""
    from contextlib import AsyncExitStack

    from mesh_net.client import connect
    from mesh_net.scene_room import COOP_SCENE, SceneRoom, check_progress, check_state, coop_files, disposable_project, parse_input
    from mesh_net.server import Server

    with disposable_project(coop_files(), scaffold=False) as root:
        room = SceneRoom(root / COOP_SCENE, root)

    async def run() -> float:
        server = Server(room)
        proxy = DelayProxy(("127.0.0.1", await server.start()), rtt_ms=100.0, seed=7)
        port = await proxy.start()
        checks = {"check": lambda m: check_state(m, room.identity, room), "check_input": parse_input,
                  "progress": check_progress}
        try:
            async with AsyncExitStack() as stack:
                a = await stack.enter_async_context(connect(port, **checks))  # type: ignore[arg-type]
                b = await stack.enter_async_context(connect(port, **checks))  # type: ignore[arg-type]
                async with asyncio.timeout(5):
                    while len((await a.receive())["players"]) < 2:
                        pass
                    sent = time.perf_counter()
                    await b.input(1, 0)
                    while next(r for r in (await b.receive())["players"] if r[0] == b.entity)[6] < b.seq:
                        pass
                return (time.perf_counter() - sent) * 1000
        finally:
            await proxy.close()
            await server.close()

    acked = asyncio.run(run())
    assert 100.0 - 1.0 <= acked <= 100.0 + 50.0 + SLACK_MS, f"acknowledged after {acked:.1f} ms"


@pytest.mark.fast
def test_a_delivery_never_comes_early_even_if_the_loop_wakes_early(monkeypatch: pytest.MonkeyPatch) -> None:
    """Before Python 3.13 the Windows event loop's clock moves in 15.6 ms steps and runs timers up to that much early
    (CI's Python 3.11 read a 100 ms round trip as 75.8 ms). ``until`` waits out the rest on perf_counter."""
    import tooling.net_delay_proxy as proxy_module

    real_sleep = asyncio.sleep

    async def early(delay: float) -> None:
        await real_sleep(0)  # (a loop that wakes at once)

    monkeypatch.setattr(proxy_module.asyncio, "sleep", early)

    async def run() -> float:
        due = time.perf_counter() + 0.03
        await proxy_module.until(due)
        return time.perf_counter() - due

    assert asyncio.run(run()) >= 0.0
