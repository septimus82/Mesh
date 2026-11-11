"""Server authority for a world of Studio-authored rooms (N7). Graphics-free: never imports Arcade or GameWindow.

The world file Studio keeps (``packs/core_regions/worlds/main.json``) lists the rooms. Each room runs N6's
authority (mesh_net.scene_room.SceneRoom). A room tagged ``expedition`` gets one instance per party; every other
room has one shared instance. Players move between rooms through the doors Studio authors (``SceneTransition``
walk-in passages and their ``spawn_point`` arrival markers). Parties are server records keyed by a stable player
id, never by a room's entity ids. See docs/networking/n7_multi_room.md.
"""

from __future__ import annotations

import copy
import enum
import hashlib
import json
import re
import secrets
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import persistence
from . import protocol as wire
from .scene_room import BOUND, Body, Player, SceneRoom, Unsupported, check_state, config, load_scene, parse_input, roll_drops

WORLD_FILE = "packs/core_regions/worlds/main.json"
EXPEDITION_TAG = "expedition"
# The packaged demonstration (tooling/make_expedition.py): where each file goes in a project.
EXPEDITION_FILES = {
    WORLD_FILE: "world.json",
    "packs/core_regions/scenes/start.json": "hub.json",
    "packs/core_regions/scenes/ancient_ruins_layer_1.json": "ruins_1.json",
    "packs/core_regions/scenes/ancient_ruins_layer_2.json": "ruins_2.json",
    "packs/core_regions/maps/start.json": "hub_map.json",
    "packs/core_regions/maps/ancient_ruins_layer_1.json": "ruins_1_map.json",
    "packs/core_regions/maps/ancient_ruins_layer_2.json": "ruins_2_map.json",
    "assets/prefabs.json": "prefabs.json",
    "assets/data/items.json": "items.json",
}
MAX_CONNECTIONS = wire.MAX_PLAYERS  # online players (mesh_net.server's accept limit)
MAX_CHARACTERS = 16  # online + retained after a disconnect, as N5
MAX_INSTANCES = 8  # room instances, the hub included
MAX_PARTY = 4
MAX_INVITES = 4  # pending invitations one player can hold
INVITE_TICKS = 60 * wire.HZ
RETAIN_TICKS = 30 * wire.HZ  # N5's resume window
KEY = re.compile(r"[a-z0-9_]{1,48}")
ROOM_ID = re.compile(r"[a-z0-9_]{1,48}:[0-9]{1,9}")
PARTY_OPS = {"create": (), "invite": ("player",), "accept": ("party",), "decline": ("party",), "leave": ()}
NOTICES = persistence.NOTICES + ("need_party", "no_instance", "room_full", "transfer_failed", "left_expedition", "in_party", "not_leader",
           "no_player", "busy", "no_invite", "party_full", "invited")


class TransferResult(enum.Enum):
    MOVED = "moved"
    NO_PARTY = "need_party"  # an expedition needs a party
    NO_INSTANCE = "no_instance"  # the instance limit is reached
    FULL = "room_full"
    FAILED = "transfer_failed"  # the destination could not be prepared; nothing changed


@dataclass(frozen=True)
class Door:
    """A walk-in SceneTransition: its area, where it leads and the arrival marker there."""

    id: str
    target: str
    spawn: str
    x: float
    y: float
    half_w: float
    half_h: float

    def touches(self, body: Body) -> bool:
        """SceneTransition.update's area test: the player picture's bounds against the area (strict overlap)."""
        hw, hh = body.width / 2, body.height / 2
        return (body.center_x - hw < self.x + self.half_w and body.center_x + hw > self.x - self.half_w
                and body.center_y - hh < self.y + self.half_h and body.center_y + hh > self.y - self.half_h)


@dataclass
class RoomDef:
    key: str
    path: str  # the scene file, project-relative (a client loads it through GameWindow.load_scene)
    label: str
    expedition: bool
    proto: SceneRoom  # validated at load; every instance starts as a copy of it
    doors: list[Door]
    arrivals: dict[str, tuple[float, float]]  # spawn id (lower case) -> marker position
    drop_tables: dict[str, dict[str, Any] | None]  # enemy id -> DropTable settings (rolled anew per instance)


@dataclass
class Instance:
    id: str
    key: str
    room: SceneRoom
    party: int | None
    touching: dict[int, frozenset[str]] = field(default_factory=dict)  # eid -> doors overlapped last tick


@dataclass
class Member:
    pid: int
    order: int  # when they joined the world (leadership passes to the longest-standing)
    online: bool = True
    instance: str | None = None
    eid: int | None = None
    player: Player | None = None  # their avatar while disconnected (retained)
    token: str | None = None  # the resume credential while disconnected
    expires: int = 0
    party: int | None = None
    sent_party: dict[str, Any] | None = None
    outbox: list[wire.Message] = field(default_factory=list)


@dataclass
class Party:
    id: int
    leader: int
    members: list[int]


def room_defs(root: Path, world_file: str = WORLD_FILE) -> tuple[str, dict[str, RoomDef]]:
    """Every room of the world file, validated as one world: (start key, {key: RoomDef})."""
    world = json.loads((root / world_file).read_text(encoding="utf-8"))
    scenes = world.get("scenes")
    if not isinstance(scenes, dict) or not scenes or len(scenes) > MAX_INSTANCES:
        raise Unsupported(f"the world needs 1 to {MAX_INSTANCES} rooms")
    defs: dict[str, RoomDef] = {}
    for key, entry in sorted(scenes.items()):
        if not KEY.fullmatch(str(key)) or not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise Unsupported(f"room '{key}' needs a short lower-case key and a scene path")
        path = root / entry["path"]
        proto = SceneRoom(path, root)  # every N6 refusal applies
        _, scene = load_scene(path)
        doors: list[Door] = []
        arrivals: dict[str, tuple[float, float]] = {}
        for e in scene["entities"]:
            if str(e.get("tag") or "").strip().lower() == "spawn_point":  # engine.scene_runtime.spawn.find_spawn_marker
                marker = str(e.get("spawn_id") or e.get("name") or "").strip().lower()
                if marker:
                    arrivals.setdefault(marker, (float(e["x"]), float(e["y"])))
            cfg = config(e, "SceneTransition")
            if cfg is not None:
                doors.append(_door(e, {**{k: e[k] for k in e if k in ("target_scene", "spawn_id")}, **cfg}))
        tags = entry.get("tags") or []
        defs[key] = RoomDef(key, entry["path"], str(entry.get("label") or key), EXPEDITION_TAG in tags, proto, doors, arrivals,
                            {i: config(e, "DropTable") for e in scene["entities"] if (i := e.get("id")) in proto.enemies})
    for d in defs.values():
        for door in d.doors:
            target = defs.get(door.target)
            if target is None:
                raise Unsupported(f"door '{door.id}' leads to '{door.target}', which is not a room of this world")
            if door.spawn and door.spawn.lower() not in target.arrivals:
                raise Unsupported(f"door '{door.id}' arrives at '{door.spawn}', which room '{door.target}' lacks")
    start = world.get("start_scene")
    if start not in defs or defs[start].expedition:
        raise Unsupported("the world's start room must be one of its rooms and not an expedition")
    return start, defs


def _door(entity: dict[str, Any], cfg: dict[str, Any]) -> Door:
    """A door the authority runs exactly as SceneTransition does, or Unsupported."""
    name = entity.get("id")
    if (cfg.get("event_type") or cfg.get("trigger_event") or cfg.get("once")
            or str(cfg.get("target_tag", "player")).strip() != "player"):
        raise Unsupported(f"door '{name}' fires on events, once, or for another tag; doors here open by walking in")
    if not cfg.get("trigger_on_touch") or cfg.get("allow_interact", True):
        raise Unsupported(f"door '{name}' must be walked into, not used with E (Studio: Walk in, not Press E)")
    if str(cfg.get("area_at") or "").strip().lower() == "base" or config(entity, "ConditionalActivator") is not None:
        raise Unsupported(f"door '{name}' stands on its base or shows on conditions (HD-2D and flags are refused)")
    try:
        w, h = float(cfg.get("area_width") or 0), float(cfg.get("area_height") or 0)
    except (TypeError, ValueError):
        w = h = 0.0
    if not (0 < w <= BOUND and 0 < h <= BOUND):
        raise Unsupported(f"door '{name}' is a picture door: its area is Arcade's hit box, which needs Arcade "
                          "(Studio: show it as an Invisible passage or Map artwork)")
    target = str(cfg.get("target_scene") or cfg.get("scene") or cfg.get("target") or "").strip()
    spawn = str(cfg.get("spawn_id") or cfg.get("target_spawn") or cfg.get("spawn_point") or "").strip()
    return Door(str(name), target, spawn, float(entity["x"]), float(entity["y"]), w / 2, h / 2)


class World:
    """Every room instance, player and party of one server. Only its owner calls step(); everything is in-process
    and deterministic, so a transfer between rooms happens inside one tick."""

    def __init__(self, root: Path, world_file: str = WORLD_FILE, store: Any = None, rules: Any = None) -> None:
        """``store`` (a mesh_net.characters.CharacterStore) and ``rules`` (progression rules) make the world's
        characters persistent (N8); without them it is N7's world exactly."""
        self.root = root
        self.start, self.defs = room_defs(root, world_file)
        self.progress = persistence.Progress.open(root, self.defs, store, rules) if store is not None else None
        identities = sorted([key, d.proto.identity, d.expedition] for key, d in self.defs.items())
        self.identity = hashlib.sha256(json.dumps(identities).encode()).hexdigest()
        for key, d in self.defs.items():  # the largest frame any room can send must fit
            worst = d.proto._worst_snapshot()
            try:
                wire.encode({"v": 1, "type": "enter", "room": f"{key}:999999999", "key": key, "entity": wire.MAX_SEQ,
                             "state": {"v": 1, **worst}})
            except wire.Invalid as exc:
                raise Unsupported(f"room '{key}' could send a frame larger than {wire.MAX_BYTES} bytes") from exc
        self.sizes = {key: d.proto._template_size() for key, d in self.defs.items()}  # read once: no file at runtime
        self.tick = 0
        self.counter = 0  # instance ids are never reused: a stale frame never names a newer room
        self.instances: dict[str, Instance] = {}
        self.party_rooms: dict[tuple[int, str], str] = {}
        self.members: dict[int, Member] = {}
        self.tokens: dict[str, int] = {}
        self.parties: dict[int, Party] = {}
        self.invites: dict[int, dict[int, tuple[int, int]]] = {}  # invitee -> {party: (inviter, expiry tick)}
        self.next_pid = self.next_party = 1
        self.prepare_hook: Any = None  # tests: a callable(key) that raises, to fail a destination's preparation
        self.shared: dict[str, Instance] = {}  # key -> the one instance of a room that is not an expedition
        # What happened to players, newest last: (tick, monotonic seconds, event, pid, detail). Bounded; diagnostics.
        self.history: deque[tuple[int, float, str, int, str]] = deque(maxlen=64)
        self.hub = self._create(self.start, None)

    # --- instances ----------------------------------------------------------------------------------

    def _create(self, key: str, party: int | None) -> Instance:
        if len(self.instances) >= MAX_INSTANCES or self.counter >= 999_999_999:  # (ROOM_ID allows 9 digits)
            raise RuntimeError("instance limit")
        if self.prepare_hook is not None:
            self.prepare_hook(key)
        d = self.defs[key]
        room = copy.deepcopy(d.proto)  # fresh: tick 0, no players, its own enemies, levers and drops
        for enemy_id, enemy in room.enemies.items():
            enemy.loot = roll_drops(d.drop_tables.get(enemy_id))  # an unseeded table rolls anew, as each game does
        self.counter += 1
        inst = Instance(f"{key}:{self.counter}", key, room, party)
        self.instances[inst.id] = inst
        if party is not None:
            self.party_rooms[(party, key)] = inst.id
        else:
            self.shared[key] = inst
        return inst

    def _destroy(self, inst: Instance) -> None:
        del self.instances[inst.id]
        if inst.party is not None:
            self.party_rooms.pop((inst.party, inst.key), None)
        else:
            self.shared.pop(inst.key, None)

    def _cleanup(self) -> None:
        """A party's expedition (its instances of every expedition room) lasts while one of its members, online or
        retained, is in any of them: going down a layer and back finds the first as the party left it. It ends in
        the tick the last one leaves."""
        inside = {i.party for m in self.members.values() if (i := self.instances.get(m.instance or "")) is not None
                  and i.party is not None and i.party == m.party}
        for inst in [i for i in self.instances.values() if i.party is not None and i.party not in inside]:
            self._destroy(inst)

    # --- sessions -----------------------------------------------------------------------------------

    def connect(self, resume: str | None, character: Any = None) -> tuple[int, str]:
        """A connection joins (resume None) or resumes. Returns (player id, the next resume credential).

        In a persistent world a join names its character (``{"id", "key"}``): a character already online is refused,
        one disconnected but retained is resumed, any other joins anew. (A resume credential works as in N7.)"""
        progress = self.progress
        if progress is None and character is not None:
            raise persistence.Refused("unexpected_character")
        state = None
        if resume is not None and character is not None:
            raise wire.Invalid("a join resumes or names a character, not both")
        if resume is None and progress is not None:
            state = progress.authenticate(character)
            held = progress.owner.get(state.id)
            if held is not None:
                if self.members[held].online:
                    raise persistence.Refused("character_in_use")
                resume = self.members[held].token  # retained: resume it (that credential is spent by this)
        if resume is not None:
            if not wire.token(resume) or resume not in self.tokens:
                raise wire.Invalid("invalid resume")
            m = self.members[self.tokens.pop(resume)]
            m.online, m.token = True, None
            inst = self.instances.get(m.instance or "")
            allowed = (inst is not None and len(inst.room.players) < wire.MAX_PLAYERS
                       and (inst.party is None or inst.party == m.party))
            player, m.player = m.player, None
            if inst is not None and allowed and player is not None:
                self._enter(m, inst, player)
            else:
                self._enter(m, self.hub, self._fresh(self.hub, self.hub.room.spawn))
            if m.party is not None:
                self._fix_leader(self.parties[m.party])
        else:
            if sum(m.online for m in self.members.values()) >= MAX_CONNECTIONS or len(self.members) >= MAX_CHARACTERS:
                raise persistence.Refused("capacity") if progress is not None else wire.Invalid("character capacity")
            m = Member(self.next_pid, self.next_pid)
            self.next_pid += 1
            self.members[m.pid] = m
            if progress is not None and state is not None:
                progress.bind(m.pid, state)
            self._enter(m, self.hub, self._fresh(self.hub, self.hub.room.spawn))
        credential = secrets.token_hex(32)
        self._log("resume" if resume is not None else "connect", m.pid, m.instance or "")
        m.token = credential  # kept, but only usable once this connection ends (disconnect files it)
        return m.pid, credential

    def disconnect(self, pid: int) -> None:
        m = self.members[pid]
        inst = self.instances[m.instance or ""]
        assert m.eid is not None
        m.player = inst.room.leave(m.eid)
        inst.touching.pop(m.eid, None)
        m.eid, m.online, m.expires, m.outbox, m.sent_party = None, False, self.tick + RETAIN_TICKS, [], None
        self._log("disconnect", pid, inst.id)
        if m.token is not None:
            self.tokens[m.token] = pid
        self.invites.pop(pid, None)
        if self.progress is not None:
            self.progress.takes.discard(pid)
            self.progress.sent.pop(pid, None)
        if m.party is not None:
            self._fix_leader(self.parties[m.party])

    def _fresh(self, inst: Instance, at: tuple[float, float]) -> Player:
        return Player(Body(at[0], at[1], *self.sizes[inst.key], inst.room.template))

    def _enter(self, m: Member, inst: Instance, player: Player) -> None:
        m.eid = inst.room.join(player)
        m.instance = inst.id
        inst.touching[m.eid] = self._doors_touched(inst, player.body)
        m.outbox = [msg for msg in m.outbox if msg["type"] != "enter"]
        m.outbox.insert(0, {"v": 1, "type": "enter", "room": inst.id, "key": inst.key, "entity": m.eid,
                            "state": inst.room.snapshot()})

    def _doors_touched(self, inst: Instance, body: Body) -> frozenset[str]:
        return frozenset(d.id for d in self.defs[inst.key].doors if d.touches(body))

    # --- requests -----------------------------------------------------------------------------------

    def input(self, pid: int, msg: wire.Message) -> None:
        """An input frame. One naming a room other than the player's current one was in flight during a transfer:
        dropped. Anything malformed raises wire.Invalid (the connection ends)."""
        m = self.members[pid]
        room = msg.get("room")
        if not isinstance(room, str) or not ROOM_ID.fullmatch(room):
            raise wire.Invalid("input names no room")
        frame = {k: v for k, v in msg.items() if k != "room"}
        if room != m.instance:
            entity: int = frame["entity"] if wire.integer(frame.get("entity"), 1) else 0
            parse_input(frame, entity)  # (still checked: a malformed frame ends the connection either way)
            return
        assert m.eid is not None
        if self.progress is not None and frame.get("action") == "take":  # (a persistent claim: the world handles it)
            parse_input(frame, m.eid)
            self.progress.takes.add(pid)
            frame = {k: v for k, v in frame.items() if k != "action"}
        self.instances[room].room.input(m.eid, frame)

    def party(self, pid: int, msg: wire.Message) -> None:
        """A party request, checked against server state. Malformed raises; refused answers with a notice."""
        op = msg.get("op")
        if not isinstance(op, str) or op not in PARTY_OPS:
            raise wire.Invalid("unknown party request")
        wire.fields(msg, "party", "op", *PARTY_OPS[op])
        if not all(wire.integer(msg[k], 1) for k in PARTY_OPS[op]):
            raise wire.Invalid("a party request names players and parties by number")
        m = self.members[pid]
        if op == "create":
            if m.party is not None:
                return self._notice(m, "in_party")
            self._new_party(m)
        elif op == "invite":
            target = self.members.get(msg["player"])
            if m.party is not None and self.parties[m.party].leader != pid:
                return self._notice(m, "not_leader")
            if target is None or not target.online or target is m:
                return self._notice(m, "no_player")
            if target.party is not None:
                return self._notice(m, "busy")
            pending = self.invites.setdefault(target.pid, {})
            party = self.parties[m.party] if m.party is not None else None
            if (party is None or party.id not in pending) and len(pending) >= MAX_INVITES:
                return self._notice(m, "busy")
            if party is None:
                party = self._new_party(m)
            pending[party.id] = (pid, self.tick + INVITE_TICKS)
            self._notice(target, "invited")
        elif op in ("accept", "decline"):
            pending = self.invites.get(pid, {})
            if msg["party"] not in pending:
                return self._notice(m, "no_invite")
            if op == "decline":
                del pending[msg["party"]]
                return None
            if m.party is not None:
                return self._notice(m, "in_party")
            party = self.parties.get(msg["party"])
            if party is None or pending[msg["party"]][0] not in party.members:  # gone, or its inviter left it
                del pending[msg["party"]]
                return self._notice(m, "no_invite")
            if len(party.members) >= MAX_PARTY:
                return self._notice(m, "party_full")
            party.members.append(pid)
            m.party = party.id
            self.invites.pop(pid, None)
            self._fix_leader(party)  # (a leader who went away meanwhile hands over to this online member)
        elif op == "leave":
            if m.party is not None:
                self._leave_party(m)
        return None

    def _new_party(self, m: Member) -> Party:
        party = Party(self.next_party, m.pid, [m.pid])
        self.next_party += 1
        self.parties[party.id] = party
        m.party = party.id
        self.invites.pop(m.pid, None)
        return party

    def _leave_party(self, m: Member) -> None:
        party = self.parties[m.party or 0]
        party.members.remove(m.pid)
        m.party = None
        inst = self.instances.get(m.instance or "")
        # (The hub always has room: online players <= MAX_CONNECTIONS == one room's MAX_PLAYERS.)
        if inst is not None and inst.party == party.id:  # their access to the party's expedition ends with it
            if m.online:
                self._move(m, inst, self.hub, self.hub.room.spawn)
                self._notice(m, "left_expedition")
            else:
                m.instance, m.player = self.hub.id, self._fresh(self.hub, self.hub.room.spawn)
        if not party.members:
            self._dissolve(party)
        else:
            self._fix_leader(party)

    def _fix_leader(self, party: Party) -> None:
        """The leader is the longest-standing online member (the current one while nobody else is online)."""
        online = [p for p in party.members if self.members[p].online]
        if online and party.leader not in online:
            party.leader = min(online, key=lambda p: self.members[p].order)
        elif party.leader not in party.members:
            party.leader = min(party.members, key=lambda p: self.members[p].order)

    def _dissolve(self, party: Party) -> None:
        del self.parties[party.id]
        for pending in self.invites.values():
            pending.pop(party.id, None)
        for inst in [i for i in self.instances.values() if i.party == party.id]:
            for m in [m for m in self.members.values() if m.instance == inst.id]:
                m.instance, m.player = self.hub.id, self._fresh(self.hub, self.hub.room.spawn)  # (retained only)
            self._destroy(inst)

    def _log(self, event: str, pid: int, detail: str = "") -> None:
        self.history.append((self.tick, time.monotonic(), event, pid, detail))

    def _notice(self, m: Member, code: str) -> None:
        if m.online and len(m.outbox) < 8:
            m.outbox.append({"v": 1, "type": "notice", "code": code})

    # --- simulation ---------------------------------------------------------------------------------

    def step(self) -> None:
        self.tick += 1
        walked: list[tuple[Member, Instance, Door]] = []
        by_room = {(m.instance, m.eid): m for m in self.members.values() if m.online}
        for inst in list(self.instances.values()):
            inst.room.step()
            doors = self.defs[inst.key].doors
            for eid, player in sorted(inst.room.players.items()):
                now = frozenset(d.id for d in doors if d.touches(player.body))
                entered = now - inst.touching.get(eid, frozenset())
                inst.touching[eid] = now
                if entered:  # (two doors at once: the first by id)
                    door = min((d for d in doors if d.id in entered), key=lambda d: d.id)
                    walked.append((by_room[(inst.id, eid)], inst, door))
        if self.progress is not None:  # deaths, claims and unlocks, with everyone still where they fought
            self.progress.after_step(self)
        for m, inst, door in walked:
            self.transfer(m, inst, door)
        for m in [m for m in self.members.values() if not m.online and m.expires <= self.tick]:
            self._expire(m)
        for pending in self.invites.values():
            for party_id in [p for p, (_, until) in pending.items() if until <= self.tick]:
                del pending[party_id]
        self._cleanup()

    def transfer(self, m: Member, source: Instance, door: Door) -> TransferResult:
        """Walk ``m`` through ``door``: resolve and prepare the destination, then leave and join in one step."""
        result = self._transfer(m, source, door)
        self._log("transfer", m.pid, f"{source.id} {door.id} {result.value}")
        return result

    def _transfer(self, m: Member, source: Instance, door: Door) -> TransferResult:
        key = door.target
        d = self.defs[key]
        if d.expedition:
            if m.party is None:
                return self._refuse(m, TransferResult.NO_PARTY)
            target = self.instances.get(self.party_rooms.get((m.party, key), ""))
        else:
            target = self.shared.get(key)  # a shared room other than the hub starts when first entered
        if target is None:
            if len(self.instances) >= MAX_INSTANCES:
                return self._refuse(m, TransferResult.NO_INSTANCE)
            try:
                target = self._create(key, m.party if d.expedition else None)
            except Exception:  # noqa: BLE001  # any preparation failure leaves the world as it was
                return self._refuse(m, TransferResult.FAILED)
        if len(target.room.players) >= wire.MAX_PLAYERS:
            return self._refuse(m, TransferResult.FULL)
        at = d.arrivals[door.spawn.lower()] if door.spawn else target.room.spawn
        return TransferResult.MOVED if self._move(m, source, target, at) else self._refuse(m, TransferResult.FAILED)

    def _refuse(self, m: Member, result: TransferResult) -> TransferResult:
        self._notice(m, result.value)
        return result

    def _move(self, m: Member, source: Instance, target: Instance, at: tuple[float, float]) -> bool:
        """Leave ``source``, join ``target`` at ``at``; on any failure joining, back where they stood (False)."""
        assert m.eid is not None
        player = self._fresh(target, at)  # (built before anything changes)
        old = source.room.leave(m.eid)  # no input for the old room applies from here on
        source.touching.pop(m.eid, None)
        present = set(target.room.players)
        try:
            self._enter(m, target, player)
        except Exception:  # noqa: BLE001  # whatever failed, the player is put back, never left in no room
            for eid in set(target.room.players) - present:  # (and no half-made avatar stays behind)
                target.room.leave(eid)
                target.touching.pop(eid, None)
            self._enter(m, source, old)
            return False
        return True

    def _expire(self, m: Member) -> None:
        self._log("expire", m.pid)
        if self.progress is not None:
            self.progress.release(m.pid)
        if m.party is not None:
            self._leave_party(m)
        if m.token is not None:
            self.tokens.pop(m.token, None)
        del self.members[m.pid]

    # --- what each player receives --------------------------------------------------------------------

    def party_view(self, m: Member) -> wire.Message:
        party = self.parties.get(m.party or 0)
        inst = self.instances[m.instance or ""]
        return {"v": 1, "type": "party", "you": m.pid, "party": party.id if party else None,
                "leader": party.leader if party else None,
                "members": [[p, self.members[p].online, self.instances[self.members[p].instance or ""].key]
                            for p in party.members] if party else [],
                "invites": sorted([party_id, inviter] for party_id, (inviter, _) in self.invites.get(m.pid, {}).items()),
                "nearby": sorted([o.pid, o.eid] for o in self.members.values() if o.online and o.instance == inst.id)}

    def deliver(self) -> dict[int, list[wire.Message]]:
        """This tick's frames per online player: queued ones (an ``enter`` first), the party view when it changed,
        then their own room's state. A player never receives another room's state."""
        states = {i: {"v": 1, "type": "room_state", "room": i, "state": inst.room.snapshot()}
                  for i, inst in self.instances.items()}
        out = {}
        for m in self.members.values():
            if m.online:
                out[m.pid] = self.take(m.pid)
                if not any(msg["type"] == "enter" for msg in out[m.pid]):
                    out[m.pid].append(states[m.instance or ""])
        return out

    def take(self, pid: int) -> list[wire.Message]:
        """Queued frames and a changed party view for one player (also sent right after connecting)."""
        m = self.members[pid]
        out, m.outbox = m.outbox, []
        view = self.party_view(m)
        if view != m.sent_party:
            m.sent_party = view
            out.insert(1 if out and out[0]["type"] == "enter" else 0, view)
        progress = self.progress
        sheet = progress.view(self, m) if progress is not None else None
        if progress is not None and sheet is not None and sheet != progress.sent.get(pid):  # (changed by a commit)
            progress.sent[pid] = sheet
            out.insert(1 if out and out[0]["type"] == "enter" else 0, sheet)
        return out


def welcome(session: str, player: int, resume: str, world: str) -> wire.Message:
    """The frame a world server answers a join with (mesh_net.server.WorldServer; check_welcome reads it)."""
    return {"v": 1, "type": "welcome", "session": session, "player": player, "resume": resume, "world": world}


# --- client-side validation (a world client checks every frame it receives) -----------------------


def check_welcome(msg: wire.Message, world: str) -> None:
    wire.fields(msg, "welcome", "session", "player", "resume", "world")
    if (not isinstance(msg["session"], str) or not re.fullmatch(r"[0-9a-f]{32}", msg["session"])
            or not wire.integer(msg["player"], 1) or not wire.token(msg["resume"])):
        raise wire.Invalid("invalid welcome")
    if msg["world"] != world:
        raise wire.Invalid("the server runs a different world")


def check_frame(msg: wire.Message, identities: dict[str, str]) -> None:
    """Any frame after the welcome: enter, room_state, party or notice. ``identities``: room key -> identity."""
    kind = msg.get("type")
    if kind == "enter":
        wire.fields(msg, "enter", "room", "key", "entity", "state")
        if (not isinstance(msg["key"], str) or msg["key"] not in identities or not wire.integer(msg["entity"], 1)
                or not _room_of(msg["room"], msg["key"])):
            raise wire.Invalid("invalid enter")
        check_state(msg["state"], identities[msg["key"]])
        if not any(row[0] == msg["entity"] for row in msg["state"]["players"]):
            raise wire.Invalid("enter without the player's own avatar")
    elif kind == "room_state":
        wire.fields(msg, "room_state", "room", "state")
        if not isinstance(msg["room"], str) or not ROOM_ID.fullmatch(msg["room"]) or not isinstance(msg["state"], dict):
            raise wire.Invalid("invalid room state")
        check_state(msg["state"])  # (its scene is checked against the room's identity by the client: it knows the key)
    elif kind == "party":
        wire.fields(msg, "party", "you", "party", "leader", "members", "invites", "nearby")
        rows = (msg["members"], msg["invites"], msg["nearby"])
        if (not wire.integer(msg["you"], 1) or not all(type(r) is list and len(r) <= wire.MAX_PLAYERS for r in rows)
                or not (msg["party"] is None or wire.integer(msg["party"], 1))
                or not (msg["leader"] is None or wire.integer(msg["leader"], 1))
                or not all(isinstance(r, list) and len(r) == 3 and wire.integer(r[0], 1) and type(r[1]) is bool
                           and isinstance(r[2], str) and r[2] in identities for r in msg["members"])
                or not all(isinstance(r, list) and len(r) == 2 and wire.integer(r[0], 1) and wire.integer(r[1], 1)
                           for r in msg["invites"] + msg["nearby"])):
            raise wire.Invalid("invalid party")
    elif kind == "character":
        persistence.check_character(msg)
    elif kind == "notice":
        wire.fields(msg, "notice", "code")
        if not isinstance(msg["code"], str) or msg["code"] not in NOTICES:
            raise wire.Invalid("invalid notice")
    else:
        raise wire.Invalid("unknown frame")


def _room_of(room: Any, key: str) -> bool:
    return isinstance(room, str) and ROOM_ID.fullmatch(room) is not None and room.rsplit(":", 1)[0] == key


def expedition_files() -> dict[str, bytes]:
    """The packaged demonstration (mesh_net/expedition) as project files, with the engine's starter tileset."""
    from importlib.resources import files  # noqa: PLC0415

    from engine.repo_root import bundled_file  # noqa: PLC0415

    from .scene_room import COOP_TILESET  # noqa: PLC0415

    out = {rel: files("mesh_net").joinpath("expedition", name).read_bytes() for rel, name in EXPEDITION_FILES.items()}
    for rel in COOP_TILESET:
        path = bundled_file(rel)
        if path is None:
            raise FileNotFoundError(f"bundled file not installed: {rel}")
        out[rel] = path.read_bytes()
    return out
