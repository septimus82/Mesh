"""Version 3 wire messages. Each bounded UTF-8 JSON object ends in LF.

Every message carries ``"v": VERSION`` and is checked exactly (``fields``). A peer speaking another version is refused
(:class:`VersionMismatch`): a server answers such a join with ``{"type": "refused", "code": "protocol_version"}`` and
closes, a client refuses any frame of another version. There is no downgrade and no v2 or v1 behaviour (owner decision
OD2, as D1 was for v2). A v2 server, whose own check is exact too, answers a v3 join with its v2 ``refused`` frame,
which a v3 client refuses for its version. JSON's ``NaN`` and ``Infinity`` are refused in any frame.

Version 2 (owner decision D1): a scene snapshot's player row carries the authority's own placement of that body
(mesh_net.scene_room.check_state):

* ``elevation``: px, a finite number within the coordinate bound, as ``mesh_entity_data["elevation"]`` holds it
  (rounded to 0.001 px); always ``0`` in a 2D room.
* ``floor``: the id of the floor it stands on, as the room's collision world names it (engine.hd2d.world:
  ``"<structure id>/<collider node>"``, or ``"ground"`` for an HD-2D room's ground); ``null`` in a 2D room, which has
  no collision world.

Version 3 (M4, owner decisions OD1-OD11, docs/plans/m4_online_combat.md) adds what responsive combat needs, all at
once, so that no later M4 stage needs a v4:

* a player row is ``[entity, x, y, facing, elevation, floor, ack, attack_seq]``. ``ack``: the ``seq`` of the input
  the authority last consumed for that player since it joined this room instance (0: none). ``attack_seq``: how many
  attacks the authority has started for that player since it joined this room instance;
* an enemy row is ``[id, hp, hit_seq, x, y, elevation, floor]``. ``hit_seq``: how many hits the enemy has taken in
  this room instance. Its placement is as a player row's (static until enemies move, M4-4; ``floor`` is ``null`` for
  a body the authority has never stood on a floor);
* every ``input`` carries ``tick``, the server tick the client means it for (OD11). An attack's cooldown is judged
  on it, as the window judged it, within [now - COOLDOWN_CLAIM_WINDOW, now] (mesh_net.scene_room.SceneRoom._may_attack): an
  older claim is stale and dropped, a later one counts as now. An attack may carry ``view_tick``, the tick (a number:
  between two ticks, a fraction) its window showed (reserved for lag compensation, M4-5). Neither lets the authority
  start more than one attack (or one use or take) a tick;
* a ``welcome`` carries ``hz``, the authority's tick rate, which must be this side's ``HZ``.

A frame is at most MAX_BYTES, and a room whose largest snapshot would not fit is refused at load (Unsupported), never
at run time. v3's longer rows lower how many enemies fit: with 8 players and floor ids at their 128-character limit,
about 25 enemies with 12-character ids, 22 with 24, 18 with 40 (fewer than the 32 networked objects allowed before).

Counters, not events, so a lost or late snapshot is never ambiguous. Within a room instance (a client takes a new
baseline at every ``welcome`` and ``enter``) no counter or acknowledgement goes back, and a client's own ``ack`` never
exceeds the last ``seq`` it sent (mesh_net.scene_room.check_progress).

Clients never send a placement: an input frame is a direction, an action and those ticks only, and a frame with any
other key is refused, so the server alone places bodies. Snapshots carry the server's ``tick``; a client accepts only a
tick newer than the last it applied. Any frame that is malformed, out of order, or inconsistent with the client's own
room (its collision world: check_state) or with what it has already applied (check_progress) is refused whole, before
anything of it is applied, and the connection ends with that reason (``Invalid``).
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

Message = dict[str, Any]
VERSION = 3
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


def input_frame(entity: int, seq: int, dx: int, dy: int, tick: int = 0, action: str | None = None,
                **extra: Any) -> Message:
    """An input frame: ``tick`` is the server tick the client means it for; ``extra`` (N7's ``room``, an attack's
    ``view_tick``) as given."""
    msg: Message = {"v": VERSION, "type": "input", "entity": entity, "seq": seq, "tick": tick, "dx": dx, "dy": dy,
                    **extra}
    if action is not None:
        msg["action"] = action
    return msg


def input_fields(msg: Message) -> None:
    """An input frame's shape (``fields``), its intended ``tick``, and a ``view_tick`` only on an attack (v3)."""
    optional = tuple(key for key in ("action", "view_tick") if key in msg)
    fields(msg, "input", "entity", "seq", "tick", "dx", "dy", *optional)
    if not integer(msg["tick"], 0):
        raise Invalid("invalid intended tick")
    if "view_tick" in msg:
        view = msg["view_tick"]
        if (msg.get("action") != "attack" or not isinstance(view, (int, float)) or isinstance(view, bool)
                or not 0 <= view <= MAX_SEQ):  # (NaN fails the comparison)
            raise Invalid("a view tick is an attack's, a tick number")


def check_hz(msg: Message) -> None:
    """A welcome's ``hz``: the authority ticks at this side's rate, which both sides' timing is built on."""
    if not integer(msg["hz"], HZ, HZ):
        raise Invalid(f"the server ticks at {repr(msg['hz'])[:16]} Hz: this Mesh plays at {HZ} Hz only")


def movement(msg: Message, entity: int) -> tuple[int, int, int, str | None]:
    input_fields(msg)
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
