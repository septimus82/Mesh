"""M4-6: rendered frames of online co-op combat under injected latency, from two hidden windows.

    py -3.13 tooling/m4_render_evidence.py OUT [--rtt-ms 100] [--jitter-ms 10] [--loss 0.01] [--rto-ms 200]
                                               [--seed 7] [--queue drain|deep|small] [--rewind on|off]

M4's demonstration world (tooling/m4_demo_world.py: the HD-2D crossing with walking bandits, and the 2D ruins through
a door) on a real authority (mesh_net.server.WorldServer) behind the M4-6 delay proxy (tooling/net_delay_proxy.py),
with two real client windows (mesh_net.world_client) joined through the proxy, both hidden and never activated
(tooling/hidden_windows.py), audio silent. Two Python processes:

- this one: the authority and the proxy on their own event loop in a thread (a window's frame never holds a tick),
  and window A on the main thread;
- window B: tooling/net_world_probe.py on the same world's files, driven over its command channel.

Every input goes through the client's own key handling (a key event dispatched to the window, as the probes do); no
OS input. The scenario, in the crossing:

1. B steps west; A walks up off the bandit's lane: **prediction**, A's avatar moving in its window before the
   server's row does (framed on the first frame that shows it);
2. A walks east over the middle of the bandit's walk and steps down to face it, then swings, pressed while A's window
   shows the bandit walking under the hitbox (lag compensation judges it where it was shown), until a
   **server-confirmed hit on the moving enemy** (at most ATTEMPTS swings, a cooldown apart): A's **local swing**
   framed as the press shows it, and 100 ms later; the hit framed inside its flash; B's window framed when its state
   first shows **A's swing**, and **the hit**;
3. both walk west through the door: a **room transfer** to the ruins under latency.

``OUT/evidence.json`` logs the link, the queue preset and lag compensation, each frame (with the marks on screen)
and every event in A's window with the client's and the server's tick: local swing shown (and the press it answers),
local move shown and server move seen (prediction), prediction correction (over 0.05 px), server-confirmed hit (with
the bandit's server x at the press and at the hit), room transfer (enter and room shown), and the authority's attack
counters. Timings are descriptive.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
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
from tooling.m4_demo_world import RUINS, START  # noqa: E402
from tooling.m4_demo_world import files as demo_files  # noqa: E402
from tooling.m4_demo_world import write as write_demo  # noqa: E402
from tooling.net_delay_proxy import RTO_MS, DelayProxy  # noqa: E402
from tooling.net_walk import walk  # noqa: E402
from tooling.net_windows import command, stop_workers  # noqa: E402
from tooling.net_world_probe import handle, hidden_arena, rendered  # noqa: E402

TARGET = "bandit_ground"  # walks east and west on the open ground, x 552-664 (tooling/m4_demo_world.py)
# Where A stands to strike: north of the bandit's lane (its feet walk y 104), over the middle of its walk (x 552-664),
# facing down. From there A's hitbox (the reach, 32 px, ahead: centred 32 px below A) covers the lane while A's own
# feet stay clear of it (A ends at y 136-154 after the step down). (target, within) for tooling/net_walk.walk.
ABOVE_LANE = (156.0, 5.0)
MID_ROUTE = (609.0, 8.0)
# px: a bandit shown within this of A's x is under the hitbox: half the hitbox (16) + half the bandit's feet collider
# (9.5), less 7.5 px (a step) to spare.
ACROSS = 18.0
ATTEMPTS = 5
CORRECTED = 0.05  # px: a reconciliation that moves the avatar further is a correction (tooling/m4_latency_probe.py)
COUNTERS = ("stale_attacks", "refused_attacks", "future_views", "clamped_views", "unseen_views", "drained_moves")


class Backend:
    """The authority (WorldServer over the demonstration world) and the delay proxy in front of it, on a loop in a
    thread."""

    def __init__(self, queue: str, rewind: bool, proxy: DelayProxy) -> None:
        from mesh_net.scene_room import disposable_project  # noqa: PLC0415
        from mesh_net.server import WorldServer  # noqa: PLC0415
        from mesh_net.world import World  # noqa: PLC0415

        depth, hold, drain = self.queue = queue_settings(preset=queue)
        with disposable_project(demo_files(), scaffold=False) as root:
            self.world = World(root, depth=depth, hold=hold, drain=drain, rewind=rewind)
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

    def room(self, pid: int) -> Any:
        """Player ``pid``'s room instance (read across threads)."""
        member = self.world.members[pid]
        if member.eid is None:  # (between rooms)
            raise KeyError(pid)
        return self.world.instances[member.instance or ""].room

    def where(self, pid: int) -> tuple[int, float, float]:
        """(tick, x, y) of player ``pid`` as the authority has it now."""
        room = self.room(pid)
        body = room.players[self.world.members[pid].eid].body
        return room.tick, body.center_x, body.center_y


class Evidence:
    """The run's log (``evidence.json``) and frames, timed from the start."""

    def __init__(self, out: Path, backend: Backend, a: Any, settings: dict[str, Any]) -> None:
        self.out, self.backend, self.a, self.t0 = out, backend, a, time.perf_counter()
        self.log: dict[str, Any] = {**settings, "frames": [], "events": [], "swings": []}
        self.taken: set[str] = set()
        self.watch: tuple[float, float] | None = None  # prediction: A's x, y before its first move (None: not watching)

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
        """Window A's picture now, read back from its framebuffer (once per moment), with the marks it shows."""
        if moment in self.taken:
            return
        self.taken.add(moment)
        name = f"{len(self.log['frames']):02d}_A_{moment}.png"
        taken = self.ms()
        self.a.draw(asyncio.get_running_loop().time())
        rendered(self.a).save(self.out / name)
        marks = [[m.mesh_name, round(m.center_x, 1), round(m.center_y, 1)] for m, *_ in self.a.view.marks]
        self.log["frames"].append({"file": name, "window": "A", "moment": moment, "t_ms": taken, "saved_ms": self.ms(),
                                   **self.ticks(), "marks": marks})

    async def frame_b(self, b: Any, moment: str) -> dict[str, Any]:
        """Window B's picture now (its own process saves it), with the marks it shows."""
        entry: dict[str, Any] = {"file": f"{len(self.log['frames']):02d}_B_{moment}.png", "window": "B",
                                 "moment": moment, "t_ms": self.ms()}
        self.log["frames"].append(entry)  # (its place first: A may frame meanwhile)
        reply: dict[str, Any] = await command(b, f"frame {self.out / entry['file']}")
        state = reply["state"] or {}
        entry.update(saved_ms=self.ms(), client_tick=state.get("tick"), room=reply["key"], marks=reply["marks"])
        return reply


def instrument(ev: Evidence) -> list[Any]:
    """Patches that log window A's events as they happen (and frame the swing and the hit's flash at once)."""
    swing, flash, reconcile, on_frame, draw = (SceneView.swing, SceneView.flash, Prediction.reconcile,
                                               WorldArena.on_frame, WorldArena.draw)

    def swung(view: Any, eid: int, own: bool, facing: int = 3) -> None:
        swing(view, eid, own, facing)
        ev.event("local_swing_shown" if own else "peer_swing_shown", entity=eid, facing=facing)
        if own:  # (a key event reaches the window at its next dispatch: the frame is taken here, as it shows)
            ev.frame_a("local_swing")

    def flashed(view: Any, enemy: str) -> None:
        flash(view, enemy)
        room = ev.backend.room(ev.a.player)
        ev.event("server_confirmed_hit", enemy=enemy, shown_x=round(view.sprites[enemy].center_x, 1),
                 server_x=round(room.enemies[enemy].body.center_x, 1))
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
        elif ev.watch is not None and "server_move_seen" not in ev.taken and arena.state is not None:
            row = next(r for r in arena.state["players"] if r[0] == arena.entity)
            if tuple(row[1:3]) != ev.watch:
                ev.taken.add("server_move_seen")
                ev.event("server_move_seen", xy=row[1:3], ack=row[6])

    shown = [0]

    def drawn(arena: Any, now: float) -> None:
        draw(arena, now)
        if len(arena.loads) != shown[0]:
            shown[0] = len(arena.loads)
            ev.event("room_shown", key=arena.key)
        if ev.watch is not None and "local_move_shown" not in ev.taken and arena.entity in arena.avatars:
            avatar = arena.avatars[arena.entity]
            if (avatar.center_x, avatar.center_y) != ev.watch:
                ev.taken.add("local_move_shown")
                row = next(r for r in arena.state["players"] if r[0] == arena.entity)
                ev.event("local_move_shown", shown_xy=[round(avatar.center_x, 2), round(avatar.center_y, 2)],
                         server_row_xy=row[1:3])
                ev.frame_a("prediction")

    return [patch.object(SceneView, "swing", swung), patch.object(SceneView, "flash", flashed),
            patch.object(Prediction, "reconcile", reconciled), patch.object(WorldArena, "on_frame", framed),
            patch.object(WorldArena, "draw", drawn)]


async def scenario(a: Any, backend: Backend, port: int, ev: Evidence, project: Path) -> None:
    render = asyncio.create_task(a.run(port))
    b = await asyncio.create_subprocess_exec(sys.executable, "-m", "tooling.net_world_probe", str(port), "--no-hint",
                                             "--project", str(project), cwd=REPO, stdin=asyncio.subprocess.PIPE,
                                             stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    lock = asyncio.Lock()  # (one command at a time on B's channel)

    async def on_a(cmd: str) -> dict[str, Any]:
        return handle(a, cmd.split())

    async def on_b(cmd: str) -> dict[str, Any]:
        async with lock:
            reply: dict[str, Any] = await command(b, cmd)
            return reply

    windows: dict[str, Callable[[str], Awaitable[dict[str, Any]]]] = {"A": on_a, "B": on_b}

    async def until(w: str, predicate: Callable[[dict[str, Any]], bool], timeout: float = 20) -> dict[str, Any]:
        async with asyncio.timeout(timeout):
            while True:
                reply = await windows[w]("state")
                if reply["phase"] == "playing" and reply["state"] and predicate(reply):
                    return reply
                await asyncio.sleep(0.02)

    async def hold(w: str, key: str, predicate: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
        await windows[w](f"press {key}")
        try:
            return await until(w, predicate)
        finally:
            await windows[w](f"release {key}")

    def row(r: dict[str, Any], entity: int) -> list[Any]:
        return next(x for x in r["state"]["players"] if x[0] == entity)

    async def watch_b(entity: int, swings: int, hits: int) -> None:
        """B's window framed when its state first shows A's swing, then the hit (each mark lives 0.2 / 0.15 s)."""
        while "B_hit" not in ev.taken:
            async with lock:
                r = await command(b, "state")
                if r["state"] and r["key"] == START:
                    if "B_swing" not in ev.taken and row(r, entity)[7] > swings:
                        ev.taken.add("B_swing")
                        await ev.frame_b(b, "peer_swing_seen")
                    hit = next(e[2] for e in r["state"]["enemies"] if e[0] == TARGET)
                    if hit > hits:
                        ev.taken.add("B_hit")
                        await ev.frame_b(b, "peer_hit_seen")
            await asyncio.sleep(0.01)

    try:
        async with asyncio.timeout(120):
            first = await until("A", lambda r: len(r["state"]["players"]) == 2, 60)
            second = await until("B", lambda r: len(r["state"]["players"]) == 2, 60)
            pa, pb, entity = first["player"], second["player"], int(first["entity"])
            ev.log["started_ms"] = ev.ms()
            ev.frame_a("start")
            await ev.frame_b(b, "start")
            x0 = backend.where(pb)[1]
            await hold("B", "LEFT", lambda r: row(r, r["entity"])[1] <= x0 - 15)  # (apart from A on screen)
            # 1. prediction: A walks up off the bandit's lane (its window moves it before the server's row does) ...
            ev.watch = tuple(row(first, entity)[1:3])

            async def first_press(cmd: str) -> dict[str, Any]:  # (the walk's first press: when the move was pressed)
                if cmd.startswith("press") and "move_pressed_ms" not in ev.log:
                    ev.log["move_pressed_ms"] = ev.ms()
                return await on_a(cmd)

            async def where() -> tuple[int, float, float]:  # (A's own avatar as its window predicts it: a release
                body = a.prediction.body                        # stops it at once, whatever the round trip)
                return int(a.state["tick"]), body.center_x, body.center_y

            await walk(first_press, "UP", *ABOVE_LANE, where)
            await until("A", lambda r: "local_move_shown" in ev.taken and "server_move_seen" in ev.taken, 5)
            ev.watch = None
            await walk(on_a, "RIGHT", *MID_ROUTE, where)  # ... east over the middle of its walk ...
            y = a.avatars[entity].center_y
            await on_a("press DOWN")  # ... and turns to face it, a step down (released once the window shows the step)
            await until("A", lambda r: a.avatars[entity].center_y < y - 1, 5)
            await on_a("release DOWN")
            await until("A", lambda r: row(r, entity)[3] == 3 and backend.where(pa)[1:] == tuple(row(r, entity)[1:3]), 5)
            # 2. swings at the walking bandit until the server confirms a hit
            seen = await on_b("state")
            watcher = asyncio.create_task(watch_b(entity, row(seen, entity)[7],
                                                  next(e[2] for e in seen["state"]["enemies"] if e[0] == TARGET)))
            ax = backend.where(pa)[1]
            ev.log["attacker"] = {"server_xy": list(backend.where(pa)[1:]), "facing": "down"}
            last = a.view.sprites[TARGET].center_x
            for _ in range(ATTEMPTS):
                while True:  # (pressed while the window shows the bandit walking across under the hitbox)
                    await asyncio.sleep(0.03)
                    x = a.view.sprites[TARGET].center_x
                    moved, last = x != last, x
                    if moved and abs(x - ax) < ACROSS:
                        break
                room = backend.room(pa)
                press = {"t_ms": ev.ms(), "shown_x": round(x, 1), "view_tick": round(a.playback.cursor, 2),
                         "server_tick": room.tick, "server_x": round(room.enemies[TARGET].body.center_x, 1)}
                ev.taken.discard("local_swing")
                ev.taken.discard("local_swing_100ms")
                await on_a("press SPACE")
                await on_a("release SPACE")
                ev.log["swings"].append(press)
                await asyncio.sleep(0.1)
                if len(ev.log["swings"]) == 1:
                    ev.frame_a("local_swing_100ms")
                try:
                    await until("A", lambda r: "hit_confirmed" in ev.taken, 1.6)
                    break
                except TimeoutError:
                    press["hit"] = False
                    await asyncio.sleep(max(0.0, 1.05 - (ev.ms() - press["t_ms"]) / 1000))  # (the cooldown)
            ev.log["swings"][-1]["hit"] = "hit_confirmed" in ev.taken
            await asyncio.wait_for(watcher, 5)
            # 3. the room transfer: both through the door to the ruins
            await asyncio.gather(*(hold(w, "LEFT", lambda r: r["key"] == RUINS) for w in windows))
            for w in windows:
                await until(w, lambda r: r["key"] == RUINS and len(r["state"]["players"]) == 2)
            await asyncio.sleep(0.3)
            ev.frame_a("ruins_after_transfer")
            await ev.frame_b(b, "ruins_after_transfer")
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
    parser.add_argument("--rewind", choices=("on", "off"), default="on")
    args = parser.parse_args(argv)
    out: Path = args.out
    if " " in str(out.resolve()):
        parser.error("OUT's path may not contain spaces (window B's command channel splits on them)")
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        parser.error(f"{out} is not empty")
    from mesh_net import protocol as wire  # noqa: PLC0415

    proxy = DelayProxy(("127.0.0.1", 0), args.rtt_ms, args.jitter_ms, args.loss, args.rto_ms, args.seed)
    backend = Backend(args.queue, args.rewind == "on", proxy)
    settings = {"rtt_ms": args.rtt_ms, "jitter_ms": args.jitter_ms, "loss": args.loss, "rto_ms": args.rto_ms,
                "seed": args.seed, "hz": wire.HZ, "rewind": args.rewind,
                "queue": dict(zip(("preset", "depth", "hold", "drain"), (args.queue, *backend.queue)))}
    port = backend.start()
    try:
        with tempfile.TemporaryDirectory(prefix="m4demo") as scratch, \
                hidden_arena(demo_files(), no_hint=True) as a:  # (the controls toast would cover every picture)
            project = write_demo(Path(scratch) / "world")  # (window B's own copy of the world's files)
            ev = Evidence(out, backend, a, settings)
            patches = instrument(ev)
            for p in patches:
                p.start()
            try:
                asyncio.run(scenario(a, backend, port, ev, project))
            finally:
                for p in patches:
                    p.stop()
                info = a.window.ctx.info
                ev.log["gl"] = [info.VENDOR, info.RENDERER]
                ev.log["proxy"] = {d: {"chunks": c.chunks, "bytes": c.bytes, "held": c.held, "held_ms": c.held_ms}
                                   for d, c in proxy.counts.items()}
                ev.log["authority"] = {key: {c: getattr(inst.room, c) for c in COUNTERS}
                                       for key, inst in backend.world.instances.items()}
                ev.log["duration_ms"] = ev.ms()
                (out / "evidence.json").write_text(json.dumps(ev.log, indent=1), encoding="utf-8")
    finally:
        backend.stop()
    print(f"{len(ev.log['frames'])} frames, {len(ev.log['events'])} events in {ev.log['duration_ms'] / 1000:.1f} s: "
          f"{out / 'evidence.json'}")


if __name__ == "__main__":
    main(sys.argv[1:])
