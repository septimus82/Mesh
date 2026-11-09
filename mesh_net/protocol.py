"""Version 1 wire messages. Each bounded UTF-8 JSON object ends in LF."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

Message = dict[str, Any]
VERSION = 1
MAX_BYTES = 8192
MAX_PLAYERS = 8
HZ = 20
WIDTH, HEIGHT = 480, 270
MAX_SEQ = (1 << 53) - 1


class Invalid(ValueError):
    """Peer violated a wire or session rule."""


def integer(value: object, low: int, high: int = MAX_SEQ) -> bool:
    return type(value) is int and low <= value <= high


def fields(msg: Message, kind: str, *keys: str) -> None:
    if set(msg) != {"v", "type", *keys} or msg.get("type") != kind or not integer(msg.get("v"), VERSION, VERSION):
        raise Invalid("invalid message shape or version")


def token(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def encode(msg: Message) -> bytes:
    data = json.dumps(msg, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode() + b"\n"
    if len(data) > MAX_BYTES:
        raise Invalid("frame too large")
    return data


def _object(pairs: list[tuple[str, Any]]) -> Message:
    result: Message = {}
    for key, value in pairs:
        if key in result:
            raise Invalid("duplicate key")
        result[key] = value
    return result


async def read(reader: asyncio.StreamReader, timeout: float = 5.0) -> Message:
    try:
        data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout)
        if len(data) > MAX_BYTES:
            raise Invalid("oversize")
        msg = json.loads(data.decode("utf-8"), object_pairs_hook=_object)
    except (ValueError, RecursionError, asyncio.LimitOverrunError) as exc:
        raise Invalid("invalid frame") from exc
    if not isinstance(msg, dict):
        raise Invalid("expected object")
    return msg


def movement(msg: Message, entity: int) -> tuple[int, int, int]:
    fields(msg, "input", "entity", "seq", "dx", "dy")
    if not integer(msg["entity"], entity, entity) or not integer(msg["seq"], 1):
        raise Invalid("invalid owner or sequence")
    dx, dy = msg["dx"], msg["dy"]
    if not integer(dx, -1, 1) or not integer(dy, -1, 1) or abs(dx) + abs(dy) > 1:
        raise Invalid("expected one cardinal direction")
    return msg["seq"], dx, dy


def snapshot(msg: Message) -> None:
    fields(msg, "state", "tick", "players")
    players = msg["players"]
    if not integer(msg["tick"], 0) or type(players) is not list or len(players) > MAX_PLAYERS:
        raise Invalid("invalid snapshot")
    ids = set()
    for row in players:
        if not isinstance(row, list) or len(row) != 3:
            raise Invalid("invalid player")
        eid, x, y = row
        if not integer(eid, 1) or eid in ids or not integer(x, 0, WIDTH) or not integer(y, 0, HEIGHT):
            raise Invalid("invalid player position or identity")
        ids.add(eid)
