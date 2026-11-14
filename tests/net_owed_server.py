"""A real mesh_net world server in its own process, for crash tests of owed completions (#496).

    python -m tests.net_owed_server STORE

Opens the character store, hosts the packaged expedition world on a free port (``mesh_net.server.WorldServer``, real
sockets, the 20 Hz clock) and prints ``READY <port>``. Characters join over the socket like any client. The test then
steers the server through commands on stdin, one JSON object a line, each answered by one JSON line on stdout when it
is done (``ANSWER {...}``; so a test waits for an answer, never for a time):

* ``{"op": "to_guardian", "characters": [ids]}``: the characters (already joined) form a party and go hub -> Layer 1
  -> Layer 2 the way the in-process tests do (``tests.test_mesh_net_world.Driver``: placed beside each door, real
  ticks through the world's own transfer rules).
* ``{"op": "kill_guardian", "character": id}``: that character strikes the Layer 2 guardian until it falls: the
  world's legitimate condition for the unlock, handled by its own ``Progress.after_step``.
* ``{"op": "leave", "characters": [ids]}``: walk back up to the hub (the expedition ends).
* ``{"op": "party_of_one", "characters": [ids]}``: each forms its own party.
* ``{"op": "enter", "characters": [ids]}``: walk into the hub's expedition door; answers each one's room key.
* ``{"op": "fault", "store": MODE, "journal": MODE}``: what the store's commit and the journal's write do from now on:
  ``null`` (work), ``"fail"`` (raise as a failing disk does), ``"exit"`` (the process dies there, ``os._exit``),
  ``"exit_after"`` (it dies just after the commit or the write is durable), and for the store ``"uncertain"`` (the
  commit happens and the server is told it failed).
* ``{"op": "state"}``: what the world's ``Progress`` holds.
* ``{"op": "step", "ticks": n}``: n more ticks at once.

``--replay-exit N`` makes the process die after N owed completions have been recorded during start-up recovery.
The process never exits by itself: the test kills it.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import threading
from pathlib import Path
from typing import Any

from mesh_net.characters import CharacterStore, StoreError
from mesh_net.persistence import expedition_rules
from mesh_net.scene_room import disposable_project
from mesh_net.server import WorldServer
from mesh_net.world import World, expedition_files
from tests.test_mesh_net_world import GUARDIAN, R2, Driver, kill, open_gate

GUARDIAN_AT = (480.0, 256.0)


class Served(Driver):
    """The test driver, stepping a served world: every tick's frames go to the sockets, as the server's clock sends
    them."""

    def __init__(self, server: WorldServer) -> None:
        super().__init__(server.world)
        self.server = server

    def step(self, n: int = 1) -> None:
        for _ in range(n):
            self.w.step()
            self.server._send(self.w.deliver())


def _mode(mode: Any, what: str) -> Any:
    def hook(point: str) -> None:
        if mode == "uncertain" and point.startswith("after"):  # the commit happened; the server is told it failed
            raise StoreError("the commit's outcome is unknown")
        if mode == "fail" and point.startswith("before"):
            raise sqlite3.OperationalError(f"disk I/O error ({what})") if what == "store" else OSError(28, f"no space ({what})")
        if (mode == "exit" and point.startswith("before")) or (mode == "exit_after" and point.startswith("after")):
            sys.stdout.flush()
            os._exit(9)

    return hook if mode else None


def _state(world: World) -> dict[str, Any]:
    progress = world.progress
    assert progress is not None
    return {"owed": len(progress.owed), "unkept": len(progress.unkept), "accepting": progress.accepting,
            "recovered": progress.recovered, "run": progress.run, "instances": sorted(world.instances)}


def _handle(driver: Served, command: dict[str, Any]) -> dict[str, Any]:
    world = driver.w
    progress = world.progress
    assert progress is not None
    op = command["op"]
    pids = [progress.owner[c] for c in command.get("characters", [])]
    if op == "to_guardian":
        for other in pids[1:]:
            driver.party(pids[0], other)
        if len(pids) == 1:
            driver.ask(pids[0], "create")
        driver.through_hub_door(*pids)
        open_gate(driver, pids[0])
        driver.to_layer_2(*pids)
        return {"rooms": [driver.room(p).key for p in pids], "ok": all(driver.room(p).key == R2 for p in pids)}
    if op == "kill_guardian":
        pid = progress.owner[command["character"]]
        kill(driver, pid, GUARDIAN_AT, 2)
        return {"dead": driver.room(pid).room.enemies[GUARDIAN].state.dead, **_state(world)}
    if op == "leave":
        for _ in range(2):
            for pid in pids:
                driver.place(pid, 128.0, 256.0)
            driver.walk_in(-1, *pids)
        return {"rooms": [driver.room(p).key for p in pids]}
    if op == "party_of_one":
        for pid in pids:
            driver.ask(pid, "create")
        return {}
    if op == "enter":
        driver.through_hub_door(*pids)
        return {"rooms": [driver.room(p).key for p in pids]}
    if op == "fault":
        progress.store.fault = _mode(command.get("store"), "store")
        assert progress.journal is not None
        progress.journal.fault = _mode(command.get("journal"), "journal")
        return {}
    if op == "step":
        driver.step(int(command.get("ticks", 1)))
        return _state(world)
    if op == "state":
        return _state(world)
    raise ValueError(f"unknown command {op!r}")


async def _serve(store_path: Path, replay_exit: int | None) -> None:
    store = CharacterStore(store_path)
    if replay_exit is not None:  # die after N commits of start-up recovery (each replayed completion is one)
        base = store.commits

        def dying(point: str) -> None:
            if point == "after_commit" and store.commits - base >= replay_exit + 1:  # (+1: begin_run's own commit)
                os._exit(9)

        store.fault = dying
    with disposable_project(expedition_files(), scaffold=False) as root:
        world = World(root, store=store, rules=expedition_rules())
    store.fault = None
    server = WorldServer(world)
    port = await server.start(0)
    driver = Served(server)
    loop = asyncio.get_running_loop()
    commands: asyncio.Queue[str] = asyncio.Queue()

    def read() -> None:
        for line in sys.stdin:
            if line.strip():
                loop.call_soon_threadsafe(commands.put_nowait, line)

    threading.Thread(target=read, daemon=True).start()
    print(f"READY {port}", flush=True)
    while True:
        command = json.loads(await commands.get())
        try:
            answer = {"ok": True, **_handle(driver, command)}
        except Exception as exc:  # noqa: BLE001  # the test reads what failed
            answer = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        print("ANSWER " + json.dumps(answer), flush=True)


class ServerProcess:
    """The test's side: starts the server process, sends it commands and reads their answers, with a time limit on
    every wait (a server that died or hung fails the test with what it wrote, instead of hanging it)."""

    def __init__(self, store: Path, *options: str, wait: float = 60.0) -> None:
        import queue
        import subprocess

        self.wait = wait
        self.proc = subprocess.Popen([sys.executable, "-m", "tests.net_owed_server", str(store), *options],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                     cwd=Path(__file__).resolve().parents[1])
        self.lines: queue.Queue[str | None] = queue.Queue()
        self.errors: list[str] = []
        threading.Thread(target=self._pump, args=(self.proc.stdout, self.lines.put), daemon=True).start()
        threading.Thread(target=self._pump, args=(self.proc.stderr, self.errors.append), daemon=True).start()
        ready = self._line("READY ")  # (None: it exited during start-up, as a recovery crash test makes it)
        self.port = int(ready) if ready is not None else 0

    @staticmethod
    def _pump(stream: Any, sink: Any) -> None:
        for line in stream:
            sink(line)
        sink(None)

    def _line(self, prefix: str) -> str | None:
        """The rest of the server's next line starting with ``prefix`` (the engine's own log lines are skipped);
        None when it has exited instead."""
        import queue

        while True:
            try:
                line = self.lines.get(timeout=self.wait)
            except queue.Empty:
                self.kill()
                raise AssertionError(f"the server process gave no answer in {self.wait} s; its errors: "
                                     f"{self.stderr()[-2000:]}") from None
            if line is None or line.startswith(prefix):
                return line if line is None else line[len(prefix):]

    def ask(self, **command: Any) -> dict[str, Any]:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(command) + "\n")
        self.proc.stdin.flush()
        line = self._line("ANSWER ")
        assert line is not None, f"the server exited instead of answering {command}: {self.stderr()[-2000:]}"
        answer: dict[str, Any] = json.loads(line)
        assert answer.pop("ok"), answer
        return answer

    def dies(self, **command: Any) -> int:
        """Send a command the server is set to die in; its exit code."""
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(command) + "\n")
        self.proc.stdin.flush()
        line = self._line("ANSWER ")
        assert line is None, f"the server answered instead of dying: {line}"
        return self.exited()

    def exited(self) -> int:
        """Wait for a server that dies by itself (during start-up recovery); its exit code."""
        import subprocess

        try:
            return self.proc.wait(self.wait)
        except subprocess.TimeoutExpired:
            self.kill()
            raise AssertionError(f"the server process did not exit in {self.wait} s") from None

    def stderr(self) -> str:
        return "".join(e for e in self.errors if e)

    def kill(self) -> int:
        """End the process at once, as a crash or a power cut would (TerminateProcess / SIGKILL): nothing it holds
        in memory is written."""
        self.proc.kill()
        code = self.proc.wait(self.wait)
        for stream in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            if stream is not None:
                stream.close()
        return code


class Client:
    """A character's socket client that keeps reading (so the server never finds it stalled while the test is busy):
    its room, its character sheet and every notice, as they arrive."""

    def __init__(self) -> None:
        self.room: str | None = None
        self.key: str | None = None
        self.sheet: dict[str, Any] | None = None
        self.notices: list[str] = []
        self.refused: str | None = None
        self.gone = False
        self._changed = asyncio.Event()

    @classmethod
    async def join(cls, port: int, credential: dict[str, str]) -> Client:
        from mesh_net import protocol as wire

        client = cls()
        client.reader, client.writer = await asyncio.open_connection("127.0.0.1", port, limit=wire.MAX_BYTES)
        client.writer.write(wire.encode({"v": 1, "type": "join", "resume": None, "character": credential}))
        client.task = asyncio.create_task(client._read())
        return client

    async def _read(self) -> None:
        from mesh_net import protocol as wire

        try:
            while True:
                msg = await wire.read(self.reader, timeout=30.0)
                kind = msg.get("type")
                if kind == "enter":
                    self.room, self.key = msg["room"], msg["key"]
                elif kind == "character":
                    self.sheet = msg
                elif kind == "notice":
                    self.notices.append(msg["code"])
                elif kind == "refused":
                    self.refused = msg["code"]
                self._changed.set()
        except (OSError, EOFError, TimeoutError, wire.Invalid, asyncio.IncompleteReadError):
            self.gone = True
            self._changed.set()

    async def until(self, predicate: Any, timeout: float = 30.0) -> None:
        """Wait for something this client has received (never for a time)."""
        async def waiting() -> None:
            while not predicate(self):
                assert not self.gone, "the connection ended first"
                self._changed.clear()
                await self._changed.wait()

        await asyncio.wait_for(waiting(), timeout)

    async def close(self) -> None:
        self.task.cancel()
        self.writer.close()
        try:
            await asyncio.wait_for(self.writer.wait_closed(), 2)
        except (OSError, TimeoutError):
            self.writer.transport.abort()


def main() -> None:
    args = sys.argv[1:]
    replay_exit = int(args[args.index("--replay-exit") + 1]) if "--replay-exit" in args else None
    asyncio.run(_serve(Path(args[0]), replay_exit))


if __name__ == "__main__":
    main()
