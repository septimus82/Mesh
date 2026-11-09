"""Bounded loopback client used by the sample and its socket tests."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
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

    async def input(self, dx: int, dy: int, action: str | None = None) -> None:
        self.seq += 1
        msg = {"v": 1, "type": "input", "entity": self.entity, "seq": self.seq, "dx": dx, "dy": dy}
        if action is not None:
            msg["action"] = action
        wire.movement(msg, self.entity)
        self.writer.write(wire.encode(msg))
        await asyncio.wait_for(self.writer.drain(), 2)

    async def receive(self) -> wire.Message:
        msg = await wire.read(self.reader)
        wire.snapshot(msg)
        if msg["tick"] <= self.state["tick"] or not any(row[0] == self.entity for row in msg["players"]):
            raise wire.Invalid("out of order or missing owner")
        self.state = msg
        return msg


@asynccontextmanager
async def connect(port: int, resume: str | None = None) -> AsyncIterator[Client]:
    reader, writer = await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port, limit=wire.MAX_BYTES), 3)
    try:
        writer.write(wire.encode({"v": 1, "type": "join", "resume": resume}))
        hello = await wire.read(reader)
        wire.fields(hello, "welcome", "entity", "session", "resume", "state")
        if (not wire.token(hello["resume"]) or not isinstance(hello["session"], str)
                or not re.fullmatch(r"[0-9a-f]{32}", hello["session"]) or not wire.integer(hello["entity"], 1)
                or not isinstance(hello["state"], dict)):
            raise wire.Invalid("invalid welcome")
        wire.snapshot(hello["state"])
        if not any(row[0] == hello["entity"] for row in hello["state"]["players"]):
            raise wire.Invalid("missing own entity")
        yield Client(reader, writer, hello["entity"], hello["session"], hello["resume"], hello["state"])
    finally:
        writer.close()
        try:
            await asyncio.wait_for(writer.wait_closed(), 2)
        except (OSError, TimeoutError):
            writer.transport.abort()
