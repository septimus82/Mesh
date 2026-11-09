"""Local authoritative TCP server. Run python -m mesh_net.server."""

from __future__ import annotations

import argparse
import asyncio
import secrets

from . import protocol as wire
from .simulation import Player, Room


class Server:
    def __init__(self) -> None:
        self.room = Room()
        self.listener: asyncio.Server | None = None
        self.clock: asyncio.Task[None] | None = None
        self.connections: dict[asyncio.Task[None], asyncio.StreamWriter] = {}
        self.peers: dict[int, asyncio.StreamWriter] = {}
        self.offline: dict[str, tuple[int, Player]] = {}

    async def start(self, port: int = 0) -> int:
        if self.listener is not None:
            raise RuntimeError("server already listening")
        self.listener = await asyncio.start_server(self._accept, "127.0.0.1", port, limit=wire.MAX_BYTES, backlog=16)
        self.clock = asyncio.create_task(self._run_clock())
        return int(self.listener.sockets[0].getsockname()[1])

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
            wire.fields(msg, "join", "resume")
            key = msg["resume"]
            if key is not None and (not wire.token(key) or key not in self.offline):
                raise wire.Invalid("invalid resume")
            if key is None and len(self.peers) + len(self.offline) >= 16:
                raise wire.Invalid("character capacity")
            eid = self.room.join(self.offline.pop(key)[1] if key is not None else None)
            self.peers[eid] = writer
            writer.write(wire.encode({"v": 1, "type": "welcome", "session": secrets.token_hex(16), "entity": eid,
                                      "resume": credential, "state": self.room.snapshot()}))
            bucket, count = self.room.tick, 0
            while True:
                msg = await wire.read(reader)
                if bucket != self.room.tick:
                    bucket, count = self.room.tick, 0
                count += 1
                if count > 8:
                    raise wire.Invalid("input rate")
                self.room.input(eid, msg)
        except (wire.Invalid, OSError, EOFError, TimeoutError):
            pass  # remote disconnects and invalid frames end this session
        finally:
            if eid is not None:
                del self.peers[eid]
                self.offline[credential] = (self.room.tick + 30 * wire.HZ, self.room.leave(eid))
            writer.transport.abort()

    async def _run_clock(self) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time()
        while True:
            deadline += 1 / wire.HZ
            await asyncio.sleep(max(0.0, deadline - loop.time()))
            # Drop excess elapsed time after a process stall, never burst queued physics steps.
            deadline = max(deadline, loop.time() - 1 / wire.HZ)
            self.room.step()
            self.offline = {k: v for k, v in self.offline.items() if v[0] > self.room.tick}
            data = wire.encode(self.room.snapshot())
            for writer in self.peers.values():
                if writer.transport.get_write_buffer_size() > 2 * wire.MAX_BYTES:
                    writer.transport.abort()
                elif not writer.is_closing():
                    writer.write(data)

    async def close(self) -> None:
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


async def serve(port: int) -> None:
    server = Server()
    try:
        bound = await server.start(port)
        print(f"Mesh room listening on 127.0.0.1:{bound}", flush=True)
        await asyncio.Future()
    finally:
        await server.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=46870)
    try:
        asyncio.run(serve(parser.parse_args().port))
    except KeyboardInterrupt:
        pass
