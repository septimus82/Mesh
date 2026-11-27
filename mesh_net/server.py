"""Local authoritative TCP server. Run python -m mesh_net.server."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import secrets
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from . import protocol as wire
from .simulation import Player, Room

logger = logging.getLogger(__name__)


class InputBudget:
    """Flood protection for one session's frames after its welcome: a token bucket on the event loop's clock.

    A client sends one input a tick (HZ a second). A network stall (a TCP retransmission) or a server stall (GC, a
    store write, a debugger) holds them back, and they then arrive together, many within one tick: a burst is normal
    and must never end the session. Each frame takes a token; the bucket refills at RATE a second up to BURST. RATE is
    twice the rate a client sends at, so a client keeping to it never runs the bucket dry, and the burst a stall of up
    to BURST / HZ seconds (3 s) builds up always fits. A session that does run it dry sends faster than any client
    and is closed, as before. Its frames are never dropped or merged instead: the frames past the limit are the newest
    ones, which a room's input queue would keep. (The bucket bounds how fast frames come; the room bounds what it
    keeps of a burst: mesh_net.scene_room.DEPTH directions, the newest, and PENDING actions of each kind, read one a
    tick. So a burst the bucket lets through never walks a body faster, nor loses an attack.)

    A new session starts with START tokens, the 8 frames at once the old per-tick limit allowed (a world client's
    most: 4 queued party requests and an input). Its bucket fills at RATE, twice as fast as a client's backlog can
    grow, so a stall straight after joining fits too, while a flood straight after joining is refused.

    The clock is ``loop.time()``, never the tick count: after a server stall the clock skips the missed ticks
    (``Server._run_clock``), but the backlog to read covers all of the stall's time.

    The server's own stalls are never held against a session (#727): ``held`` (``Server.held``) says how long the
    server's loop has been held up, and each second of it adds HZ tokens over BURST, the frames a client keeping to
    HZ sent meanwhile. Without it, a stall over BURST / HZ (a store commit slow to reach the disk) ended every session
    at once. That credit is for the stall's backlog, which arrives at once, and nothing else: tokens over BURST drain
    back to it at RATE (never refill), and a session never holds more than BURST + CREDIT (CREDIT: a client's 5 s
    read timeout, wire.read, which ends an honest session in any longer stall). So a session quiet after a stall
    cannot bank it, nor add up stalls or a slow server's lateness: a few seconds on, its burst is BURST again.
    """

    # (RATE and BURST are fixed from wire.HZ at import: HZ is implicit on both sides of the wire, so changing it
    # is a protocol change anyway.)
    RATE = 2 * wire.HZ  # tokens a second
    BURST = 3 * wire.HZ  # 3 s of a client's input: a 2 s stall's backlog (40) with room to spare
    START = 8
    CREDIT = 5 * wire.HZ  # the most stall credit over BURST: 5 s of a client's input

    def __init__(self, held: Callable[[], float] = lambda: 0.0) -> None:
        self.clock = asyncio.get_running_loop().time
        self.tokens, self.at = float(self.START), self.clock()
        self.held, self.seen = held, held()

    def take(self) -> bool:
        """Spend a token on one frame; False when there is none (the session must end)."""
        now, held = self.clock(), self.held()
        elapsed = (now - self.at) * self.RATE
        if self.tokens > self.BURST:  # (a stall's credit, left after its backlog: drains back to BURST)
            refill = max(self.BURST, self.tokens - elapsed)
        else:
            refill = min(self.BURST, self.tokens + elapsed)
        self.tokens = min(self.BURST + self.CREDIT, refill + (held - self.seen) * wire.HZ)
        self.at, self.seen = now, held
        if self.tokens < 1:
            return False
        self.tokens -= 1
        return True


class Server:
    def __init__(self, room: Any = None) -> None:
        self.room = room if room is not None else Room()  # or a mesh_net.scene_room.SceneRoom: same interface
        self.listener: asyncio.Server | None = None
        self.clock: asyncio.Task[None] | None = None
        self.connections: dict[asyncio.Task[None], asyncio.StreamWriter] = {}
        self.peers: dict[int, asyncio.StreamWriter] = {}
        self.offline: dict[str, tuple[int, Player]] = {}
        self._lifecycle = asyncio.Lock()
        self.due: float | None = None  # (loop time) when the clock's current tick is due
        self.stalled = 0.0  # seconds the loop was held up beyond a tick, as the clock has counted them

    def held(self) -> float:
        """Seconds this server's loop has been held up beyond a tick (a step, a store write, GC, the process paused),
        counting a hold-up the clock has not yet run since: what InputBudget never holds against a session."""
        if self.due is None:
            return self.stalled
        return self.stalled + max(0.0, asyncio.get_running_loop().time() - self.due - 1 / wire.HZ)

    async def _next_tick(self, loop: asyncio.AbstractEventLoop) -> None:
        """Wait for the next tick. Excess elapsed time after a stall is dropped (counted in ``stalled``), never burst
        as queued steps."""
        if self.due is None:
            self.due = loop.time()
        self.due += 1 / wire.HZ
        await asyncio.sleep(max(0.0, self.due - loop.time()))
        late = loop.time() - self.due - 1 / wire.HZ
        if late > 0:
            self.stalled += late
            self.due += late

    async def start(self, port: int = 0) -> int:
        async with self._lifecycle:
            if self.listener is not None:
                raise RuntimeError("server already listening")
            listener = await asyncio.start_server(self._accept, "127.0.0.1", port, limit=wire.MAX_BYTES, backlog=16)
            try:
                clock = asyncio.create_task(self._run_clock())
                port = int(listener.sockets[0].getsockname()[1])
            except BaseException:
                listener.close()
                await listener.wait_closed()
                raise
            self.listener, self.clock = listener, clock
            return port

    def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if self.listener is None or len(self.connections) >= wire.MAX_PLAYERS:
            writer.transport.abort()
            return
        task = asyncio.create_task(self._handle(reader, writer))
        self.connections[task] = writer
        task.add_done_callback(self._finished)

    def _finished(self, task: asyncio.Task[None]) -> None:
        self.connections.pop(task, None)
        if not task.cancelled():
            task.result()  # surface programming errors in the event loop

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        eid = None
        credential = secrets.token_hex(32)
        try:
            msg = await wire.read(reader)
            try:
                wire.fields(msg, "join", "resume")
            except wire.VersionMismatch as exc:
                await self._refuse(writer, exc)
                raise
            key = msg["resume"]
            if key is not None and (not wire.token(key) or key not in self.offline):
                raise wire.Invalid("invalid resume")
            if key is None and len(self.peers) + len(self.offline) >= 16:
                raise wire.Invalid("character capacity")
            eid = self.room.join(self.offline[key][1] if key is not None else None)
            self.offline.pop(key, None)  # (only once joined: a refused join keeps the retained character)
            self.peers[eid] = writer
            writer.write(wire.encode({"v": wire.VERSION, "type": "welcome", "session": secrets.token_hex(16),
                                      "entity": eid, "resume": credential, "state": self.room.snapshot(),
                                      "hz": wire.HZ}))
            budget = InputBudget(self.held)
            while True:
                msg = await wire.read(reader)
                if not budget.take():
                    raise wire.Invalid("input rate")
                self.room.input(eid, msg)
        except wire.Invalid as exc:
            logger.info("[Mesh][Net] session closed: %s", exc)  # invalid frames, or too many (InputBudget)
        except (OSError, EOFError, TimeoutError):
            pass  # remote disconnects end this session
        finally:
            if eid is not None:
                del self.peers[eid]
                self.offline[credential] = (self.room.tick + 30 * wire.HZ, self.room.leave(eid))
            writer.transport.abort()

    @staticmethod
    async def _refuse(writer: asyncio.StreamWriter, exc: Exception) -> None:
        """Say why a join is refused before closing, when the refusal has a code (wire.VersionMismatch: another
        protocol version; mesh_net.persistence.Refused)."""
        code = getattr(exc, "code", None)
        if code is not None:
            writer.write(wire.encode({"v": wire.VERSION, "type": "refused", "code": code}))
            await asyncio.wait_for(writer.drain(), 2)

    async def _run_clock(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            await self._next_tick(loop)
            self.room.step()
            self.offline = {k: v for k, v in self.offline.items() if v[0] > self.room.tick}
            data = wire.encode(self.room.snapshot())
            for writer in self.peers.values():
                if writer.transport.get_write_buffer_size() > 2 * wire.MAX_BYTES:
                    writer.transport.abort()
                elif not writer.is_closing():
                    writer.write(data)

    async def close(self) -> None:
        async with self._lifecycle:
            listener, self.listener = self.listener, None
            if listener is not None:
                listener.close()
            tasks = list(self.connections)
            if self.clock is not None:
                tasks.append(self.clock)
                self.clock = None
            for writer in self.connections.values():
                writer.transport.abort()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if listener is not None:
                await listener.wait_closed()
            self.offline.clear()
            self.due = None  # (a later start's clock starts afresh, not late by the time it was stopped)


class WorldServer(Server):
    """Hosts a mesh_net.world.World (N7): many rooms, parties and transfers. The world decides what each player
    receives; this class only moves frames."""

    def __init__(self, world: Any) -> None:
        super().__init__(world)
        self.world = world

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        pid = None
        try:
            msg = await wire.read(reader)
            try:
                wire.fields(msg, "join", "resume", *(("character",) if "character" in msg else ()))
                pid, credential = self.world.connect(msg["resume"], msg.get("character"))
            except Exception as exc:
                await self._refuse(writer, exc)  # (another protocol version, or mesh_net.persistence.Refused)
                raise
            self.peers[pid] = writer
            from .world import welcome  # noqa: PLC0415  # (the world's own frame builder)

            writer.write(wire.encode(welcome(secrets.token_hex(16), pid, credential, self.world.identity)))
            for frame in self.world.take(pid):
                writer.write(wire.encode(frame))
            budget = InputBudget(self.held)
            while True:
                msg = await wire.read(reader)
                if not budget.take():
                    raise wire.Invalid("request rate")
                kind = msg.get("type")
                if kind == "input":
                    self.world.input(pid, msg)
                elif kind == "party":
                    self.world.party(pid, msg)
                else:
                    raise wire.Invalid("unknown request")
        except wire.Invalid as exc:
            logger.info("[Mesh][Net] session closed: %s", exc)  # invalid frames, or too many (InputBudget)
        except (OSError, EOFError, TimeoutError):
            pass  # remote disconnects end this session
        finally:
            if pid is not None:
                del self.peers[pid]
                self.world.disconnect(pid)
            writer.transport.abort()

    async def _run_clock(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            await self._next_tick(loop)
            try:
                self.world.step()
                self._send(self.world.deliver())
            except Exception:
                # A broken world must not keep accepting players it no longer steps: say so and shut everything.
                logger.exception("[Mesh][Net] the world failed; closing the server")
                if self.listener is not None:
                    self.listener.close()
                for connection in list(self.connections.values()):
                    connection.transport.abort()
                raise

    def _send(self, delivery: dict[int, list[wire.Message]]) -> None:
        encoded: dict[int, bytes] = {}  # one encoding per frame object (a room's state is shared by its players)
        for pid, frames in delivery.items():
            writer = self.peers.get(pid)
            if writer is None or writer.is_closing():
                continue
            if writer.transport.get_write_buffer_size() > 4 * wire.MAX_BYTES:
                writer.transport.abort()
                continue
            for frame in frames:
                data = encoded.get(id(frame))
                if data is None:
                    data = encoded[id(frame)] = wire.encode(frame)
                writer.write(data)


async def serve(port: int, room: Any = None, host: type[Server] = Server) -> None:
    server = host(room)
    try:
        bound = await server.start(port)
        print(f"Mesh room listening on 127.0.0.1:{bound}", flush=True)
        assert server.clock is not None
        await server.clock  # runs until stopped; if the room or world fails, the process ends with its error
    finally:
        await server.close()


QUEUE_NAMES = ("depth", "hold", "drain")


def rewind_from(args: argparse.Namespace, environ: Any = os.environ) -> bool:
    """A scene or world server's lag compensation (M4-5): ``--rewind on|off``, else MESH_NET_REWIND (1 or 0), else the
    game's own (mesh_net.scene_room.REWIND); anything else is refused (ValueError)."""
    from .scene_room import REWIND  # noqa: PLC0415

    flag = getattr(args, "rewind", None)
    if flag is not None:
        return bool(flag == "on")
    value = environ.get("MESH_NET_REWIND")
    if value is None:
        return REWIND
    if value not in ("0", "1"):
        raise ValueError(f"MESH_NET_REWIND must be 1 (on) or 0 (off), not {value[:16]!r}")
    return bool(value == "1")


def queue_from(args: argparse.Namespace, environ: Any = os.environ) -> dict[str, int]:
    """A scene or world server's input-queue settings (mesh_net.scene_room.queue_settings): a preset from ``--queue``
    (else MESH_NET_QUEUE, else the provisional default), each knob from its flag (``--input-depth``, ``--input-hold``,
    ``--input-drain``), else MESH_NET_INPUT_DEPTH / _HOLD / _DRAIN, else the preset's; checked, ValueError naming
    what was wrong."""
    from .scene_room import queue_settings  # noqa: PLC0415

    preset = getattr(args, "queue", None) or environ.get("MESH_NET_QUEUE")
    values: dict[str, Any] = {}
    for name in QUEUE_NAMES:
        value, env = getattr(args, f"input_{name}", None), f"MESH_NET_INPUT_{name.upper()}"
        if value is None and environ.get(env) is not None:
            try:
                value = int(environ[env])
            except ValueError:
                raise ValueError(f"{env} must be a whole number, not {environ[env][:16]!r}") from None
        values[name] = value
    return dict(zip(QUEUE_NAMES, queue_settings(**values, preset=preset)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=46870)
    parser.add_argument("--coop", action="store_true", help="host the packaged co-op scene (mesh_net/coop)")
    parser.add_argument("--expedition", action="store_true",
                        help="host the packaged hub and expedition rooms (mesh_net/expedition)")
    parser.add_argument("--store", help="with --expedition: keep characters in this character store (N8; it must "
                                        "exist: python -m mesh_net.characters new-store PATH)")
    from .scene_room import QUEUE, QUEUE_PRESETS  # noqa: PLC0415

    parser.add_argument("--queue", choices=sorted(QUEUE_PRESETS), help="with --coop or --expedition: the input queue's "
                        f"preset ({QUEUE} is the provisional default; else MESH_NET_QUEUE): " + "; ".join(
                            f"{k} = depth {d}, hold {h}, drain {r}" for k, (d, h, r) in QUEUE_PRESETS.items()))
    for name, what in (("depth", "inputs that may wait (1-20)"),
                       ("hold", "ticks a direction is walked counting the one that reads it (1-5)"),
                       ("drain", "drop the oldest waiting input when more than one has waited this many ticks in a "
                                 "row (2-20; 0 off)")):
        parser.add_argument(f"--input-{name}", type=int, help=f"with --coop or --expedition: the input queue's {name}: "
                                                              f"{what}; else MESH_NET_INPUT_{name.upper()}, else the "
                                                              "preset's")
    parser.add_argument("--rewind", choices=("on", "off"), help="with --coop or --expedition: lag compensation (M4-5: "
                        "an attack's targets judged where its window showed them, at most 300 ms back); else "
                        "MESH_NET_REWIND (1/0), else on")
    args = parser.parse_args()
    if args.store and not args.expedition:
        parser.error("--store needs --expedition")
    try:
        queue = queue_from(args)
        rewind = rewind_from(args)
    except ValueError as exc:
        parser.error(str(exc))
    store_path = Path(args.store).resolve() if args.store else None  # (before the room folder becomes the cwd)
    with ExitStack() as stack:
        room: Any = None
        host: type[Server] = Server
        if args.expedition:
            from .characters import StoreUnavailable
            from .scene_room import disposable_project
            from .world import World, expedition_files

            store = None
            if store_path is not None:
                from .characters import CharacterStore
                from .persistence import expedition_rules

                try:
                    store = CharacterStore(store_path)
                except StoreUnavailable as exc:
                    raise SystemExit(f"[Mesh][Net] {exc}") from None
                stack.callback(store.close)
            root = stack.enter_context(disposable_project(expedition_files(), scaffold=False))
            try:
                world = World(root, store=store, rules=expedition_rules() if store is not None else None,
                              depth=queue["depth"], hold=queue["hold"], drain=queue["drain"], rewind=rewind)
            except StoreUnavailable as exc:  # (the journal of owed completions cannot be used: mesh_net.owed)
                raise SystemExit(f"[Mesh][Net] {exc}") from None
            room, host = world, WorldServer
            if world.progress is not None:
                stack.callback(world.progress.close)
                print(f"Mesh characters {store_path.name if store_path else ''}", flush=True)
                if world.progress.recovered or world.progress.owed:
                    print(f"Mesh owed completions: {world.progress.recovered} recorded from earlier runs, "
                          f"{len(world.progress.owed)} still owed", flush=True)
            print(f"Mesh world {world.identity[:12]}", flush=True)
        elif args.coop:
            from .scene_room import COOP_SCENE, SceneRoom, coop_files, disposable_project

            root = stack.enter_context(disposable_project(coop_files(), scaffold=False))
            room = SceneRoom(root / COOP_SCENE, root, **queue, rewind=rewind)
            print(f"Mesh scene {room.identity[:12]}", flush=True)
        if args.coop or args.expedition:
            print("Mesh input queue " + " ".join(f"{k} {v}" for k, v in queue.items()), flush=True)
            print(f"Mesh lag compensation {'on' if rewind else 'off'}", flush=True)
        try:
            asyncio.run(serve(args.port, room, host))
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
