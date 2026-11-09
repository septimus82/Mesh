"""Seeded application-message disruption experiment, using a virtual 200 Hz clock."""

from __future__ import annotations

import argparse
import asyncio
import heapq
import json
import random
from statistics import mean, median, quantiles
from time import perf_counter

from . import protocol as wire
from .playback import Playback
from .simulation import Room


def study(*, lag_ms: int = 75, jitter_ms: int = 40, loss: float = 0.1, seed: int = 42) -> dict:
    if not (0 <= lag_ms <= 1000 and 0 <= jitter_ms <= 1000 and 0 <= loss < 1):
        raise ValueError("delay/jitter 0..1000 ms and loss 0..<1")
    rng = random.Random(seed)
    room, view = Room(), Playback()
    eid = room.join()
    view.push(room.snapshot(), 0)
    pending: list[tuple[int, int, dict]] = []
    serial = dropped = stale = size = 0
    errors = []
    seq = 0

    def send(msg: dict, now: int) -> None:
        nonlocal serial, dropped
        serial += 1
        if rng.random() < loss:
            dropped += 1
        else:
            delay = max(0, lag_ms + rng.randint(-jitter_ms, jitter_ms))
            heapq.heappush(pending, (now + delay, serial, msg))

    def deliver(now: int) -> None:
        nonlocal stale
        while pending and pending[0][0] <= now:
            _, _, msg = heapq.heappop(pending)
            if msg["type"] == "input":
                room.input(eid, msg)
            elif not view.push(msg, now / 1000):
                stale += 1

    for ms in range(0, 6000, 5):
        if ms % 50 == 0:
            seq += 1
            dx = (1 if ms // 1000 % 2 == 0 else -1) if ms < 4000 else 0
            send({"v": 1, "type": "input", "entity": eid, "seq": seq, "dx": dx, "dy": 0}, ms)
        deliver(ms)
        if ms % 50 == 0:
            room.step()
            state = room.snapshot()
            size += len(wire.encode(state))
            send(state, ms)
            deliver(ms)
        errors.append(abs(view.positions(ms / 1000)[eid][0] - room.players[eid].x))
    return {"lag_ms": lag_ms, "jitter_ms": jitter_ms, "loss": loss, "seed": seed, "ticks": room.tick,
            "dropped_messages": dropped, "old_snapshots_discarded": stale, "mean_display_error_px": round(mean(errors), 2),
            "max_display_error_px": round(max(errors), 2), "final_error_px": errors[-1], "snapshot_payload_bytes_per_sec": round(size / 6, 1)}


async def loopback_study(seed: int = 42) -> dict:
    """Time one client's intent until the other reads its first matching position."""
    from .client import connect
    from .server import Server

    server = Server()
    port = await server.start()
    rng = random.Random(seed)
    samples = []
    try:
        async with connect(port) as sender, connect(port) as observer:
            for i in range(40):
                await sender.input(0, 0)
                state = await observer.receive()
                # Drain intervening states and allow the zero intent to take effect.
                target = server.room.tick + 2
                while state["tick"] < target:
                    state = await observer.receive()
                await observer.input(0, 0)
                origin = state["players"][0][1]
                dx = 1 if i % 2 == 0 else -1
                await asyncio.sleep(rng.random() * 0.045)
                start = perf_counter()
                await sender.input(dx, 0)
                async with asyncio.timeout(2):
                    while (state["players"][0][1] - origin) * dx <= 0:
                        state = await observer.receive()
                samples.append((perf_counter() - start) * 1000)
            return {"samples": len(samples), "seed": seed, "median_ms": round(median(samples), 2),
                    "p95_ms": round(quantiles(samples, n=20, method="inclusive")[-1], 2),
                    "max_ms": round(max(samples), 2), "last_snapshot_bytes": len(wire.encode(state))}
    finally:
        await server.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lag-ms", type=int, default=75)
    parser.add_argument("--jitter-ms", type=int, default=40)
    parser.add_argument("--loss", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--loopback", action="store_true", help="measure actual two-socket input visibility")
    options = vars(parser.parse_args())
    result = asyncio.run(loopback_study(options["seed"])) if options.pop("loopback") else study(**options)
    print(json.dumps(result, indent=2))
