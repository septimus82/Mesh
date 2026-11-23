"""Version 2 wire messages. Each bounded UTF-8 JSON object ends in LF.

Every message carries ``"v": VERSION`` and is checked exactly (``fields``). A peer speaking another version is refused
(:class:`VersionMismatch`): a server answers such a join with ``{"type": "refused", "code": "protocol_version"}`` and
closes, a client refuses any frame of another version. There is no downgrade and no v1 behaviour. (A v1 server, whose
own check is exact too, closes on a v2 join without a word.) JSON's ``NaN`` and ``Infinity`` are refused in any frame.

Version 2 (owner decision D1): a scene snapshot's player row is ``[entity, x, y, facing, elevation, floor]``
(mesh_net.scene_room.check_state), the authority's own placement of that body:

* ``elevation``: px, a finite number within the coordinate bound, as ``mesh_entity_data["elevation"]`` holds it
  (rounded to 0.001 px); always ``0`` in a 2D room.
* ``floor``: the id of the floor it stands on, as the room's collision world names it (engine.hd2d.world:
  ``"<structure id>/<collider node>"``, or ``"ground"`` for an HD-2D room's ground); ``null`` in a 2D room, which has
  no collision world.

Clients never send any of it: an input frame is a direction and an action only, and a frame with any other key is
refused, so the server alone places bodies. Snapshots carry the server's ``tick``; a client accepts only a tick newer
than the last it applied. Any frame that is malformed, out of order or inconsistent with the client's own room (its
collision world, mesh_net.scene_room.check_state) is refused whole, before anything of it is applied, and the
connection ends with that reason (``Invalid``).
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

Message = dict[str, Any]
VERSION = 2
MAX_BYTES = 8192
MAX_PLAYERS = 8
HZ = 20
WIDTH, HEIGHT = 480, 270
ENEMY_AT = (220, 135)
ENEMY_HP = 2
MAX_SEQ = (1 << 53) - 1


class Invalid(ValueError):
    """Peer violated a wire or session rule."""


class VersionMismatch(Invalid):
    """The peer speaks another protocol version: refused at the handshake, never downgraded."""

    code = "protocol_version"  # (the ``refused`` frame's code, as mesh_net.persistence.Refused's)


def integer(value: object, low: int, high: int = MAX_SEQ) -> bool:
    return type(value) is int and low <= value <= high


def fields(msg: Message, kind: str, *keys: str) -> None:
    if "v" not in msg:
        raise Invalid("invalid message shape (no version)")  # (malformed, not another version)
    if not integer(msg["v"], VERSION, VERSION):
        raise VersionMismatch(f"protocol version {repr(msg['v'])[:16]}: this Mesh speaks version {VERSION} only")
    if set(msg) != {"v", "type", *keys} or msg.get("type") != kind:
        raise Invalid("invalid message shape")


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


def _constant(name: str) -> Any:
    raise Invalid(f"{name} is not a number on the wire")


async def read(reader: asyncio.StreamReader, timeout: float = 5.0) -> Message:
    try:
        data = await asyncio.wait_for(reader.readuntil(b"\n"), timeout)
        if len(data) > MAX_BYTES:
            raise Invalid("oversize")
        msg = json.loads(data.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant)
    except (ValueError, RecursionError, asyncio.LimitOverrunError) as exc:
        raise Invalid("invalid frame") from exc
    if not isinstance(msg, dict):
        raise Invalid("expected object")
    return msg


def movement(msg: Message, entity: int) -> tuple[int, int, int, str | None]:
    optional = ("action",) if "action" in msg else ()
    fields(msg, "input", "entity", "seq", "dx", "dy", *optional)
    action = msg.get("action")
    if action not in (None, "attack", "take"):
        raise Invalid("unknown action")
    if not integer(msg["entity"], entity, entity) or not integer(msg["seq"], 1):
        raise Invalid("invalid owner or sequence")
    dx, dy = msg["dx"], msg["dy"]
    if not integer(dx, -1, 1) or not integer(dy, -1, 1) or abs(dx) + abs(dy) > 1:
        raise Invalid("expected one cardinal direction")
    return msg["seq"], dx, dy, action


def snapshot(msg: Message) -> None:
    fields(msg, "state", "tick", "players", "enemy_hp", "pickup", "holder")
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
    hp, pickup, holder = msg["enemy_hp"], msg["pickup"], msg["holder"]
    if not integer(hp, 0, ENEMY_HP) or type(pickup) is not bool or (pickup and hp):
        raise Invalid("invalid encounter state")
    if holder is not None and (not integer(holder, 1) or holder not in ids or hp or pickup):
        raise Invalid("invalid pickup holder")
