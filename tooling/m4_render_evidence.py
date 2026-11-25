"""M4-6 groundwork: rendered frames of online co-op combat under injected latency, from two hidden windows.

    py -3.13 tooling/m4_render_evidence.py OUT [--rtt-ms 100] [--jitter-ms 10] [--loss 0.01] [--rto-ms 200]
                                               [--seed 7] [--queue drain|deep|small]

The packaged expedition (mesh_net.server --expedition's world) on a real authority (mesh_net.server.WorldServer)
behind the M4-6 delay proxy (tooling/net_delay_proxy.py), with two real client windows (mesh_net.world_client) joined
through the proxy, both hidden and never activated (tooling/hidden_windows.py), audio silent. Two Python processes:

- this one: the authority and the proxy on their own event loop in a thread (a window's frame never holds a tick),
  and window A on the main thread;
- window B: tooling/net_world_probe.py, driven over its command channel.

Every input goes through the client's own key handling (a key event dispatched to the window, as the probes do); no
OS input. The scenario: both meet in the hub and form a party, travel to Layer 1 (a room transfer), A opens its gate,
both go on to Layer 2 (another transfer), A walks onto the guardian and swings once. Frames are read back from each
window's framebuffer at those moments, and when A's window first shows a local swing, the server-confirmed hit (its
0.15 s flash) and B's window the peer's swing and hit. Neither window shows the first room's controls hint (the
client never ticks the HUD, so it would cover every picture). ``OUT/evidence.json`` logs the link, the input-queue preset,
each frame and every event in A's window (local swing shown, prediction correction over 0.05 px, server-confirmed
hit, room transfer: the enter and the room shown) with the client's and the server's tick. Timings are descriptive.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):  # (run as a script: the checkout's packages)
    sys.path.insert(0, str(REPO))

import pyglet  # noqa: E402

pyglet.options["audio"] = ("silent",)  # never the sound card (a swing and a hit play sounds): before anything uses it

from mesh_net.scene_client import SceneView  # noqa: E402
from mesh_net.scene_room import Prediction, queue_settings  # noqa: E402
from mesh_net.world_client import WorldArena  # noqa: E402
from tooling.net_delay_proxy import RTO_MS, DelayProxy  # noqa: E402
from tooling.net_walk import ABOVE, GAP, ON_ENEMY, walk  # noqa: E402
from tooling.net_windows import command, stop_workers  # noqa: E402
from tooling.net_world_probe import handle, hidden_arena, rendered  # noqa: E402

HUB, R1, R2 = "start", "ancient_ruins_layer_1", "ancient_ruins_layer_2"
GATE1 = f"{R1}_gate_432_256_0_0"
CORRECTED = 0.05  # px: a reconciliation that moves the avatar further is a correction (tooling/m4_latency_probe.py)


class Backend:
    """The authority (WorldServer over the expedition) and the delay proxy in front of it, on a loop in a thread."""

    def __init__(self, queue: str, proxy: DelayProxy) -> None:
        from mesh_net.scene_room import disposable_project  # noqa: PLC0415
        from mesh_net.server import WorldServer  # noqa: PLC0415
        from mesh_net.world import World, expedition_files  # noqa: PLC0415

        depth, hold, drain = self.queue = queue_settings(preset=queue)
        with disposable_project(expedition_files(), scaffold=False) as root:
            self.world = World(root, depth=depth, hold=hold, drain=drain)
        self.server, self.proxy = WorldServer(self.world), proxy
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)

    def start(self) -> int:
        self.thread.start()

        async def up() -> int:
            self.proxy.target = ("127.0.0.1", await self.server.start())
            return await self.proxy.start()

        return asyncio.run_coroutine_threadsafe(up(), self.loop).result(10)

    def stop(self) -> None:
        async def down() -> None:
            await self.proxy.close()
            await self.server.close()

        asyncio.run_coroutine_threadsafe(down(), self.loop).result(10)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5)
        self.loop.close()

    def where(self, pid: int) -> tuple[int, float, float, str | None]:
        """(tick, x, y, room key) of player ``pid`` as the authority has it now (read across threads: floats)."""
        member = self.world.members[pid]
        instance = self.world.instances[member.instance or ""]
        if member.eid is None:  # (between rooms)
            raise KeyError(pid)
        body = instance.room.players[member.eid].body
        return instance.room.tick, body.center_x, body.center_y, instance.key


class Evidence:
    """The run's log (``evidence.json``) and frames, timed from the start."""

    def __init__(self, out: Path, backend: Backend, a: Any, settings: dict[str, Any]) -> None:
        self.out, self.backend, self.a, self.t0 = out, backend, a, time.perf_counter()
        self.log: dict[str, Any] = {**settings, "frames": [], "events": []}
        self.taken: set[str] = set()

    def ms(self) -> float:
        return round((time.perf_counter() - self.t0) * 1000, 1)

    def ticks(self) -> dict[str, Any]:
        a = self.a
        server = None
        try:
            server = self.backend.where(a.player)[0]
        except KeyError:  # (not joined yet, or between rooms)
            pass
        return {"client_tick": a.state["tick"] if a.state else None, "server_tick": server, "room": a.key}

    def event(self, kind: str, **facts: Any) -> None:
        self.log["events"].append({"t_ms": self.ms(), "window": "A", "kind": kind, **self.ticks(), **facts})

    def frame_a(self, moment: str) -> None:
        """Window A's picture now, read back from its framebuffer (once per moment)."""
        if moment in self.taken:
            return
        self.taken.add(moment)
        name = f"{len(self.log['frames']):02d}_A_{moment}.png"
        self.a.draw(asyncio.get_running_loop().time())
        rendered(self.a).save(self.out / name)
        self.log["frames"].append({"file": name, "window": "A", "moment": moment, "t_ms": self.ms(), **self.ticks()})

    async def frame_b(self, b: Any, moment: str) -> dict[str, Any]:
        name = f"{len(self.log['frames']):02d}_B_{moment}.png"
        reply: dict[str, Any] = await command(b, f"frame {self.out / name}")
        state = reply["state"] or {}
        self.log["frames"].append({"file": name, "window": "B", "moment": moment, "t_ms": self.ms(),
                                   "client_tick": state.get("tick"), "room": reply["key"]})
        return reply


def instrument(ev: Evidence) -> list[Any]:
    """Patches that log window A's events as they happen (and frame the hit's 0.15 s flash at once)."""
    swing, flash, reconcile, on_frame, draw = (SceneView.swing, SceneView.flash, Prediction.reconcile,
                                               WorldArena.on_frame, WorldArena.draw)

    def swung(view: Any, eid: int, own: bool) -> None:
        swing(view, eid, own)
        ev.event("local_swing_shown" if own else "peer_swing_shown", entity=eid)
        if own:  # (a key event reaches the window at its next dispatch: the frame is taken here, as it shows)
            ev.frame_a("local_swing")

    def flashed(view: Any, enemy: str) -> None:
        flash(view, enemy)
        ev.event("server_confirmed_hit", enemy=enemy)
        ev.frame_a("hit_confirmed")

    def reconciled(prediction: Any, state: Any, own: int) -> tuple[float, float, bool]:
        result: tuple[float, float, bool] = reconcile(prediction, state, own)
        if result[0] > CORRECTED:
            ev.event("prediction_correction", px=round(result[0], 2), elevation_px=result[1], floor_changed=result[2])
        return result

    def framed(arena: Any, msg: Any, now: float) -> None:
        on_frame(arena, msg, now)
        if msg["type"] == "enter":
            ev.event("room_transfer_enter", to=msg["key"])

    shown = [0]

    def drawn(arena: Any, now: float) -> None:
        draw(arena, now)
        if len(arena.loads) != shown[0]:
            shown[0] = len(arena.loads)
            ev.event("room_shown", key=arena.key)

    return [patch.object(SceneView, "swing", swung), patch.object(SceneView, "flash", flashed),
            patch.object(Prediction, "reconcile", reconciled), patch.object(WorldArena, "on_frame", framed),
            patch.object(WorldArena, "draw", drawn)]


async def scenario(a: Any, backend: Backend, port: int, ev: Evidence) -> None:
    render = asyncio.create_task(a.run(port))
    b = await asyncio.create_subprocess_exec(sys.executable, "-m", "tooling.net_world_probe", str(port), "--no-hint",
                                             cwd=REPO, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                             stderr=asyncio.subprocess.STDOUT)
    windows: dict[str, Callable[[str], Awaitable[dict[str, Any]]]] = {}

    async def on_a(cmd: str) -> dict[str, Any]:
        return handle(a, cmd.split())

    async def on_b(cmd: str) -> dict[str, Any]:
        reply: dict[str, Any] = await command(b, cmd)
        return reply

    windows.update(A=on_a, B=on_b)
    pids: dict[str, int] = {}

    async def until(w: str, predicate: Callable[[dict[str, Any]], bool], timeout: float = 20) -> dict[str, Any]:
        async with asyncio.timeout(timeout):
            while True:
                reply = await windows[w]("state")
                if reply["phase"] == "playing" and reply["state"] and predicate(reply):
                    return reply
                await asyncio.sleep(0.025)

    async def hold(w: str, key: str, predicate: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
        await windows[w](f"press {key}")
        try:
            return await until(w, predicate)
        finally:
            await windows[w](f"release {key}")

    async def tap(w: str, key: str) -> None:
        await windows[w](f"press {key}")
        await windows[w](f"release {key}")

    async def go(w: str, key: str, target: float, within: float) -> None:
        async def where() -> tuple[int, float, float]:
            return backend.where(pids[w])[:3]

        await walk(windows[w], key, target, within, where)

    def facing(r: dict[str, Any]) -> int:
        return int(next(x for x in r["state"]["players"] if x[0] == r["entity"])[3])  # 0 right, 1 up, 2 left, 3 down

    def own_row(r: dict[str, Any], entity: int) -> list[Any]:
        return next(x for x in r["state"]["players"] if x[0] == entity)

    try:
        async with asyncio.timeout(240):
            first = await until("A", lambda r: len(r["state"]["players"]) == 2, 60)
            second = await until("B", lambda r: len(r["state"]["players"]) == 2, 60)
            pids.update(A=first["player"], B=second["player"])
            ev.log["started_ms"] = ev.ms()
            ev.frame_a("hub")
            await ev.frame_b(b, "hub")
            await tap("A", "P")  # a party: A creates it, invites the nearest player; B accepts
            await until("A", lambda r: bool(r["party"] and r["party"]["party"]))
            await tap("A", "I")
            await until("B", lambda r: bool(r["party"] and r["party"]["invites"]))
            await tap("B", "Y")
            for w in windows:
                await until(w, lambda r: len(r["party"]["members"]) == 2)
            await asyncio.gather(*(hold(w, "RIGHT", lambda r: r["key"] == R1) for w in windows))  # transfer 1
            for w in windows:
                await until(w, lambda r: r["key"] == R1 and len(r["state"]["players"]) == 2)
            ev.frame_a("layer1_after_transfer")
            await ev.frame_b(b, "layer1_after_transfer")
            await go("A", "RIGHT", 352, 16)  # A opens the gate with its lever (tests/test_mesh_net_gpu.py's walk)
            await go("A", "UP", 300, 16)
            await hold("A", "UP", lambda r: facing(r) == 1)
            await tap("A", "E")
            for w in windows:
                await until(w, lambda r: r["state"]["open"] == [GATE1])
            await go("A", "DOWN", *GAP)
            await go("B", "RIGHT", 250, 40)
            await go("B", "UP", *GAP)
            await asyncio.gather(*(hold(w, "RIGHT", lambda r: r["key"] == R2) for w in windows))  # transfer 2
            for w in windows:
                await until(w, lambda r: r["key"] == R2 and len(r["state"]["players"]) == 2)
            ev.frame_a("layer2_after_transfer")
            await ev.frame_b(b, "layer2_after_transfer")
            await go("A", "RIGHT", 430, 16)  # onto the guardian from above: its feet stop A at y 268, facing it
            await go("A", "UP", *ABOVE)
            await go("A", "RIGHT", 480, 16)
            await go("A", "DOWN", *ON_ENEMY)
            await until("A", lambda r: facing(r) == 3)
            entity = int(a.entity)  # (A's avatar in this room instance)
            seen = await on_b("state")
            swings_before = own_row(seen, entity)[7]
            hits_before = {e[0]: e[2] for e in seen["state"]["enemies"]}
            ev.log["swing_pressed_ms"] = ev.ms()
            await on_a("press SPACE")  # the window shows its own swing at once (OD4): framed as it does (instrument)
            await on_a("release SPACE")
            await until("A", lambda r: "local_swing" in ev.taken, 5)
            await asyncio.sleep(0.1)
            ev.frame_a("local_swing_100ms")
            await until("B", lambda r: own_row(r, entity)[7] > swings_before, 5)
            await ev.frame_b(b, "peer_swing_seen")
            await until("B", lambda r: any(e[2] > hits_before.get(e[0], 0) for e in r["state"]["enemies"]), 5)
            await ev.frame_b(b, "peer_hit_seen")
            await until("A", lambda r: "hit_confirmed" in ev.taken, 5)
            ev.log["finished_ms"] = ev.ms()
    finally:
        ev.log["window_b_problems"] = await stop_workers([b])
        a.stop()
        await render


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("out", type=Path, help="a new or empty folder for the frames and evidence.json")
    parser.add_argument("--rtt-ms", type=float, default=100.0)
    parser.add_argument("--jitter-ms", type=float, default=10.0)
    parser.add_argument("--loss", type=float, default=0.01)
    parser.add_argument("--rto-ms", type=float, default=RTO_MS)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--queue", choices=("drain", "deep", "small"), default="drain")
    args = parser.parse_args(argv)
    out: Path = args.out
    if " " in str(out.resolve()):
        parser.error("OUT's path may not contain spaces (window B's command channel splits on them)")
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        parser.error(f"{out} is not empty")
    from mesh_net import protocol as wire  # noqa: PLC0415
    from mesh_net.world import expedition_files  # noqa: PLC0415

    proxy = DelayProxy(("127.0.0.1", 0), args.rtt_ms, args.jitter_ms, args.loss, args.rto_ms, args.seed)
    backend = Backend(args.queue, proxy)
    settings = {"rtt_ms": args.rtt_ms, "jitter_ms": args.jitter_ms, "loss": args.loss, "rto_ms": args.rto_ms,
                "seed": args.seed, "hz": wire.HZ,
                "queue": dict(zip(("preset", "depth", "hold", "drain"), (args.queue, *backend.queue)))}
    port = backend.start()
    try:
        with hidden_arena(expedition_files(), no_hint=True) as a:  # (the controls toast would cover every picture)
            ev = Evidence(out, backend, a, settings)
            patches = instrument(ev)
            for p in patches:
                p.start()
            try:
                asyncio.run(scenario(a, backend, port, ev))
            finally:
                for p in patches:
                    p.stop()
                info = a.window.ctx.info
                ev.log["gl"] = [info.VENDOR, info.RENDERER]
                ev.log["proxy"] = {d: {"chunks": c.chunks, "bytes": c.bytes, "held": c.held, "held_ms": c.held_ms}
                                   for d, c in proxy.counts.items()}
                ev.log["duration_ms"] = ev.ms()
                (out / "evidence.json").write_text(json.dumps(ev.log, indent=1), encoding="utf-8")
    finally:
        backend.stop()
    print(f"{len(ev.log['frames'])} frames, {len(ev.log['events'])} events in {ev.log['duration_ms'] / 1000:.1f} s: "
          f"{out / 'evidence.json'}")


if __name__ == "__main__":
    main(sys.argv[1:])
