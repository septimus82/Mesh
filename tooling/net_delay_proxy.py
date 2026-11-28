"""M4-6: a TCP delay proxy for the online demo (docs/plans/m4_online_combat.md, §4 "M4-6 groundwork as implemented").

    py -3.13 tooling/net_delay_proxy.py --listen PORT --target HOST:PORT --rtt-ms MS [--jitter-ms MS] [--loss P]
                                        [--rto-ms MS] [--seed N]

It sits between a client and a server (mesh_net.server, mesh_net.scene_client, mesh_net.world_client: clients connect
to 127.0.0.1:PORT) and holds every chunk of bytes in each direction for the link model M4-0's probe measures with
(``Link``, used by tooling/m4_latency_probe.py): a one-way delay of RTT/2, plus uniform jitter of +-``--jitter-ms``,
and with probability ``--loss`` a stall as a lost segment's retransmission would cost (RTT + ``--rto-ms`` more).
A chunk never arrives before the one read before it (head-of-line, as TCP): jitter and stalls never reorder bytes.
Each connection draws its two links from one ``--seed``ed stream, in the order connections arrive, so a run's
delays repeat (the chunking itself is the OS's). Standard library only; it listens on loopback only.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import math
import random
import sys
import time
from dataclasses import dataclass, field
from typing import Any

RTO_MS = 200.0  # a lost segment arrives RTT + this later (Linux's RTO is SRTT + 4 RTTVAR, at least 200 ms)
CHUNK = 65536


@dataclass
class Link:
    """One direction of a TCP connection: each message's arrival time (ms), in send order."""

    one_way_ms: float
    jitter_ms: float
    loss: float
    rng: random.Random
    rto_ms: float = RTO_MS
    last: float = -math.inf

    def arrival(self, sent: float) -> float:
        delay = max(0.0, self.one_way_ms + self.rng.uniform(-self.jitter_ms, self.jitter_ms))
        if self.rng.random() < self.loss:
            delay += 2 * self.one_way_ms + self.rto_ms  # retransmitted after a timeout: RTT + rto_ms
        self.last = max(self.last, sent + delay)  # head-of-line: never before the one sent earlier
        return self.last


@dataclass
class Counts:
    """One direction's traffic over every connection: chunks and bytes passed, and the chunks held longer than the
    delay and jitter allow (a stall, or waiting behind one)."""

    chunks: int = 0
    bytes: int = 0
    held: int = 0
    held_ms: list[float] = field(default_factory=list)


class DelayProxy:
    """Accepts on 127.0.0.1 and joins each connection to ``target`` through two ``Link``s (up: client to server)."""

    def __init__(self, target: tuple[str, int], rtt_ms: float = 0.0, jitter_ms: float = 0.0, loss: float = 0.0,
                 rto_ms: float = RTO_MS, seed: int = 0) -> None:
        if not (rtt_ms >= 0 and jitter_ms >= 0 and 0 <= loss < 1 and rto_ms >= 0):
            raise ValueError("rtt, jitter and rto must be >= 0 ms and loss within [0, 1)")
        self.target, self.rtt_ms, self.jitter_ms, self.loss, self.rto_ms = target, rtt_ms, jitter_ms, loss, rto_ms
        self.rng = random.Random(seed)
        self.counts = {"up": Counts(), "down": Counts()}
        self.connections = 0
        self.server: asyncio.Server | None = None
        self.tasks: set[asyncio.Task[Any]] = set()

    def link(self) -> Link:
        return Link(self.rtt_ms / 2, self.jitter_ms, self.loss, random.Random(self.rng.random()), self.rto_ms)

    async def start(self, port: int = 0) -> int:
        self.server = await asyncio.start_server(self._accept, "127.0.0.1", port)
        fine_timer(True)
        return int(self.server.sockets[0].getsockname()[1])

    async def close(self) -> None:
        if self.server is not None:
            self.server.close()
            fine_timer(False)
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        if self.server is not None:
            await self.server.wait_closed()

    async def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.current_task()
        assert task is not None
        self.tasks.add(task)
        self.connections += 1
        up, down = self.link(), self.link()  # (drawn in arrival order, before anything can fail: one seed, one run)
        far: asyncio.StreamWriter | None = None
        try:
            far_reader, far = await asyncio.open_connection(*self.target)
            await together(self._pipe(reader, far, up, self.counts["up"]),
                           self._pipe(far_reader, writer, down, self.counts["down"]))
        except (OSError, asyncio.IncompleteReadError):
            pass  # (either end went away: both are closed below, as the network would)
        finally:
            for w in (writer, far):
                if w is not None:
                    w.transport.abort()
            self.tasks.discard(task)

    async def _pipe(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, link: Link, counts: Counts) -> None:
        """Reads ``reader`` and writes each chunk to ``writer`` at its ``link`` arrival; an end of stream goes the same
        way (after the chunks before it). A queue in between, so reading never waits for a delivery."""
        queue: asyncio.Queue[tuple[float, bytes]] = asyncio.Queue()
        allowed = link.one_way_ms + link.jitter_ms + 1e-6

        async def read() -> None:
            while True:
                data = await reader.read(CHUNK)
                now = time.perf_counter() * 1000
                due = link.arrival(now)
                if data:
                    counts.chunks += 1
                    counts.bytes += len(data)
                    if due - now > allowed:
                        counts.held += 1
                        counts.held_ms.append(round(due - now, 1))
                queue.put_nowait((due, data))
                if not data:
                    return

        async def deliver() -> None:
            while True:
                due, data = await queue.get()
                await until(due / 1000)
                if not data:
                    if writer.can_write_eof():
                        writer.write_eof()
                    return
                writer.write(data)
                await writer.drain()

        await together(read(), deliver())


async def until(due: float) -> None:
    """Waits until ``time.perf_counter()`` reaches ``due`` (s), never returning sooner. Before Python 3.13 the event
    loop's clock on Windows is GetTickCount64, in 15.6 ms steps, and the loop runs a timer up to that much early (a
    100 ms round trip read 75.8 ms on CI's Python 3.11). So the loop sleeps the bulk and a worker thread's
    ``time.sleep`` (fine on every version) the rest; on a fine loop clock the rest is ~0 and no thread is used."""
    wait = due - time.perf_counter()
    if wait > 0:
        await asyncio.sleep(wait)
    rest = due - time.perf_counter()
    if rest > 0:
        await asyncio.to_thread(time.sleep, rest)


def fine_timer(on: bool) -> None:
    """Windows: a 1 ms system timer while a proxy runs (timeBeginPeriod / timeEndPeriod, paired). asyncio's Windows
    loop otherwise wakes on the default 15.6 ms timer, which added 0-15.6 ms to every delay (measured: 100 ms RTT read
    121-124 ms). Elsewhere nothing."""
    if sys.platform == "win32":
        import ctypes  # noqa: PLC0415

        winmm = ctypes.WinDLL("winmm")
        (winmm.timeBeginPeriod if on else winmm.timeEndPeriod)(1)


async def together(*jobs: Any) -> None:
    """Runs ``jobs`` to their ends; the first to fail ends them all, with its error (none left running)."""
    tasks = [asyncio.ensure_future(job) for job in jobs]
    try:
        pending: set[asyncio.Future[Any]] = set(tasks)
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_EXCEPTION)
            for task in done:
                task.result()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--listen", type=int, required=True, help="the port clients connect to, on 127.0.0.1")
    parser.add_argument("--target", required=True, help="HOST:PORT of the server (mesh_net.server's --port)")
    parser.add_argument("--rtt-ms", type=float, default=0.0, help="round trip added: each direction holds half")
    parser.add_argument("--jitter-ms", type=float, default=0.0, help="+- uniform, each direction (never reordering)")
    parser.add_argument("--loss", type=float, default=0.0, help="chance a chunk stalls as a retransmission would")
    parser.add_argument("--rto-ms", type=float, default=RTO_MS, help="a stalled chunk waits RTT + this much more")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    host, _, port = args.target.rpartition(":")
    if not host or not port.isdigit():
        parser.error("--target must be HOST:PORT")
    try:
        proxy = DelayProxy((host, int(port)), args.rtt_ms, args.jitter_ms, args.loss, args.rto_ms, args.seed)
    except ValueError as exc:
        parser.error(str(exc))

    async def serve() -> None:
        bound = await proxy.start(args.listen)
        print(f"delay proxy 127.0.0.1:{bound} -> {args.target}: rtt {args.rtt_ms:g} ms, jitter +-{args.jitter_ms:g} ms, "
              f"loss {args.loss:g} (rto {args.rto_ms:g} ms), seed {args.seed}", flush=True)
        try:
            await asyncio.Event().wait()
        finally:
            await proxy.close()

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(serve())


if __name__ == "__main__":
    main(sys.argv[1:])
