"""Bounded loopback client used by the sample and its socket tests."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from . import protocol as wire


@dataclass
class Client:
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    entity: int
    session: str
    resume: str
    state: wire.Message
    seq: int = 0
    check: Callable[[wire.Message], None] = wire.snapshot  # a room's state validator (mesh_net.scene_room.check_state)
    check_input: Callable[[wire.Message, int], object] = wire.movement
    # (before, after, own entity, last seq sent): a room's checks across states (mesh_net.scene_room.check_progress)
    progress: Callable[[wire.Message, wire.Message, int, int], None] | None = None

    async def input(self, dx: int, dy: int, action: str | None = None) -> None:
        self.seq += 1
        msg = wire.input_frame(self.entity, self.seq, dx, dy, self.state["tick"] + 1, action)  # (the next tick)
        self.check_input(msg, self.entity)
        self.writer.write(wire.encode(msg))
        await asyncio.wait_for(self.writer.drain(), 2)

    async def receive(self) -> wire.Message:
        msg = await wire.read(self.reader)
        self.check(msg)
        if msg["tick"] <= self.state["tick"] or not any(row[0] == self.entity for row in msg["players"]):
            raise wire.Invalid("out of order or missing owner")
        if self.progress is not None:
            self.progress(self.state, msg, self.entity, self.seq)
        self.state = msg
        return msg


@asynccontextmanager
async def connect(port: int, resume: str | None = None, check: Callable[[wire.Message], None] = wire.snapshot,
                  check_input: Callable[[wire.Message, int], object] = wire.movement,
                  progress: Callable[[wire.Message, wire.Message, int, int], None] | None = None,
                  ) -> AsyncIterator[Client]:
    reader, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port, limit=wire.MAX_BYTES), 3)
    try:
        writer.write(wire.encode({"v": wire.VERSION, "type": "join", "resume": resume}))
        hello = await wire.read(reader)
        if hello.get("type") == "refused":  # (the server said why: another protocol version)
            wire.fields(hello, "refused", "code")
            raise wire.Invalid(f"refused ({str(hello['code'])[:32]})")
        wire.fields(hello, "welcome", "entity", "session", "resume", "state", "hz")
        if (not wire.token(hello["resume"]) or not isinstance(hello["session"], str)
                or not re.fullmatch(r"[0-9a-f]{32}", hello["session"]) or not wire.integer(hello["entity"], 1)
                or not isinstance(hello["state"], dict)):
            raise wire.Invalid("invalid welcome")
        wire.check_hz(hello)
        check(hello["state"])
        if not any(row[0] == hello["entity"] for row in hello["state"]["players"]):
            raise wire.Invalid("missing own entity")
        yield Client(reader, writer, hello["entity"], hello["session"], hello["resume"], hello["state"], 0, check, check_input,
                     progress)
    finally:
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), 2)
        except (OSError, TimeoutError):
            writer.transport.abort()
