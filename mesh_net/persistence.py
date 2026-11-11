"""Persistent characters inside a mesh_net.world.World (N8). Graphics-free; optional (a world without it is N7's).

The world keeps rooms, positions and parties in memory (they reset with the server). This keeps what must last in
the character store (mesh_net.characters): which character a connection controls, the items it picks up and the
unlocks it earns. Rules:

* Loot is personal. When an enemy dies, every character in that room instance at that moment is entitled to its
  own drop (the enemy's DropTable, rolled by N6's ``roll_drops``). A character claims it with "take" beside the
  enemy. Claim and inventory update are one transaction; a claim is granted once (the store refuses a second), and
  until it commits the drop stays claimable. Items only: a drop's gold is not kept (no currency in N8).
* Unlocks come from the world's progression rules (a file next to the world, validated at load): "defeating
  enemy E in room R unlocks K". Every character in that instance when E dies earns K, and one completion; the
  store counts each completion once. Unknown keys are refused at load.
* One connection controls a character at a time; another is refused while it is online.
"""

from __future__ import annotations

import json
import math
import re
import secrets
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from engine.interaction import DEFAULT_INTERACT_MAX_DIST

from . import protocol as wire
from .characters import (
    ITEM_ID,
    MAX_GRANTS,
    UNLOCK_KEY,
    AccessDenied,
    CharacterState,
    CharacterStore,
    DuplicateClaim,
    InventoryFull,
    StoreError,
)
from .scene_room import Unsupported, roll_drops

if TYPE_CHECKING:
    from .world import Instance, Member, RoomDef, World

PENDING_LIMIT = 64  # completions waiting for a store that failed
NOTICES = ("picked_up", "inventory_full", "storage_failed", "unlocked")


class Refused(wire.Invalid):
    """A join the server answers with a reason before closing (``code``)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


REFUSALS = ("character_required", "access_denied", "character_in_use", "capacity", "storage_failed", "unexpected_character")


@dataclass
class Rule:
    key: str
    label: str
    room: str
    defeat: str


def load_rules(data: Any, defs: dict[str, RoomDef]) -> list[Rule]:
    """The progression rules, checked against the world: every key well formed, every room an expedition room of
    this world and every enemy one of that room's."""
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("unlocks"), dict):
        raise Unsupported("progression rules need version 1 and an 'unlocks' table")
    rules = []
    for key, rule in sorted(data["unlocks"].items()):
        if not UNLOCK_KEY.fullmatch(str(key)) or not isinstance(rule, dict) or set(rule) != {"label", "room", "defeat"}:
            raise Unsupported(f"unlock '{key}' needs a short lower-case key, a label, a room and an enemy to defeat")
        room = defs.get(rule["room"])
        if room is None or not room.expedition or rule["defeat"] not in room.proto.enemies:
            raise Unsupported(f"unlock '{key}': '{rule['defeat']}' is not an enemy of expedition room '{rule['room']}'")
        rules.append(Rule(key, str(rule["label"])[:64], rule["room"], rule["defeat"]))
    return rules


def item_limits(root: Path, defs: dict[str, RoomDef]) -> dict[str, int]:
    """Every item the world's enemies can drop, from the project's item database (engine.inventory), with the most
    one character may hold. A drop naming an item the database lacks is refused at load."""
    from engine.inventory import ItemDatabase  # noqa: PLC0415  # (uncached: this world's own file)

    try:
        database = ItemDatabase.load(root)
    except (OSError, ValueError) as exc:
        raise Unsupported(f"the world's item database (assets/data/items.json) cannot be read: {exc}") from exc
    limits = {item.id: (item.max_stack if item.stackable else 1) for item in database.items.values()
              if ITEM_ID.fullmatch(item.id)}
    for d in defs.values():
        for enemy, table in d.drop_tables.items():
            for drop in (table or {}).get("drops") or []:
                item = drop.get("item_id") if isinstance(drop, dict) else None
                if item and str(item).strip() not in limits:
                    raise Unsupported(f"enemy '{enemy}' drops '{item}', which assets/data/items.json does not define")
    return limits


@dataclass
class Progress:
    """The persistent half of a world: characters by connection, loot entitlements, completions."""

    store: CharacterStore
    rules: list[Rule]
    run: str = field(default_factory=lambda: secrets.token_hex(8))  # claims are scoped to one server run
    characters: dict[int, CharacterState] = field(default_factory=dict)  # pid -> its character (cached after commits)
    owner: dict[str, int] = field(default_factory=dict)  # character id -> the pid controlling it (online or retained)
    takes: set[int] = field(default_factory=set)
    defeated: dict[str, set[str]] = field(default_factory=dict)  # instance -> enemies whose death was handled
    loot: dict[str, dict[tuple[str, str], list[tuple[str, int]]]] = field(default_factory=dict)  # inst -> (enemy, cid)
    pending: deque[tuple[str, str, str]] = field(default_factory=lambda: deque(maxlen=PENDING_LIMIT))
    sent: dict[int, wire.Message] = field(default_factory=dict)

    @classmethod
    def open(cls, root: Path, defs: dict[str, RoomDef], store: CharacterStore, rules: Any) -> Progress:
        progress = cls(store, load_rules(rules, defs))
        store.stack_limits = item_limits(root, defs)
        store.unlock_keys = frozenset(r.key for r in progress.rules)
        store.begin_run(progress.run)
        return progress

    # --- sessions -------------------------------------------------------------------------------------

    def authenticate(self, credential: Any) -> CharacterState:
        if not isinstance(credential, dict) or set(credential) != {"id", "key"}:
            raise Refused("character_required")
        try:
            return self.store.authenticate(credential["id"], credential["key"])
        except AccessDenied as exc:
            raise Refused("access_denied") from exc
        except StoreError as exc:
            raise Refused("storage_failed") from exc

    def bind(self, pid: int, state: CharacterState) -> None:
        self.characters[pid] = state
        self.owner[state.id] = pid

    def release(self, pid: int) -> None:
        """The member is gone (expired): its character is free to be taken up again."""
        state = self.characters.pop(pid, None)
        if state is not None and self.owner.get(state.id) == pid:
            del self.owner[state.id]
        self.takes.discard(pid)
        self.sent.pop(pid, None)

    # --- simulation -----------------------------------------------------------------------------------

    def after_step(self, world: World) -> None:
        for inst in list(world.instances.values()):
            for enemy_id, enemy in inst.room.enemies.items():
                if enemy.state.dead and enemy_id not in self.defeated.setdefault(inst.id, set()):
                    self.defeated[inst.id].add(enemy_id)
                    self._defeated(world, inst, enemy_id)
        for pid in sorted(self.takes):
            m = world.members.get(pid)
            if m is not None and m.online:
                self._take(world, m)
        self.takes.clear()
        for _ in range(len(self.pending)):  # completions a failed store owes (retried each tick, bounded)
            self._complete(world, *self.pending.popleft())
        for gone in [i for i in self.defeated if i not in world.instances]:  # temporary state ends with its room
            self.defeated.pop(gone, None)
            self.loot.pop(gone, None)

    def _present(self, world: World, inst: Instance) -> list[Member]:
        return [m for m in world.members.values() if m.online and m.instance == inst.id and m.pid in self.characters]

    def _defeated(self, world: World, inst: Instance, enemy_id: str) -> None:
        table = world.defs[inst.key].drop_tables.get(enemy_id)
        present = self._present(world, inst)
        for m in present:
            grants = [(str(d["item_id"]).strip(), d["quantity"]) for d in roll_drops(table) if d["item_id"]][:MAX_GRANTS]
            if grants:
                self.loot.setdefault(inst.id, {})[(enemy_id, self.characters[m.pid].id)] = grants
        for rule in self.rules:
            if rule.room == inst.key and rule.defeat == enemy_id:
                for m in present:
                    self._complete(world, self.characters[m.pid].id, f"{inst.id}/{enemy_id}", rule.key)

    def _complete(self, world: World, cid: str, completion: str, key: str) -> None:
        pid = self.owner.get(cid)
        try:
            fresh, state = self.store.complete(cid, self.run, completion, key)
        except DuplicateClaim:
            return
        except StoreError:
            self.pending.append((cid, completion, key))
            if pid is not None:
                world._notice(world.members[pid], "storage_failed")
            return
        if pid is not None:
            self.characters[pid] = state
            if fresh:
                world._notice(world.members[pid], "unlocked")

    def _take(self, world: World, m: Member) -> None:
        """Claim the nearest drop this character is entitled to, within interaction reach."""
        inst = world.instances[m.instance or ""]
        cid = self.characters[m.pid].id
        body = inst.room.players[m.eid or 0].body
        near = []
        for enemy_id, owner in self.loot.get(inst.id, {}):
            enemy = inst.room.enemies[enemy_id]
            distance = math.hypot(enemy.body.center_x - body.center_x, enemy.body.center_y - body.center_y)
            if owner == cid and distance <= DEFAULT_INTERACT_MAX_DIST:  # (engine.interaction's reach)
                near.append((distance, enemy_id))
        near.sort()
        if not near:
            return
        enemy_id = near[0][1]
        grants = self.loot[inst.id][(enemy_id, cid)]
        try:
            state = self.store.claim(cid, self.run, f"{inst.id}/{enemy_id}", grants)
        except DuplicateClaim:  # (already granted: the entitlement is spent)
            del self.loot[inst.id][(enemy_id, cid)]
            return
        except InventoryFull:
            world._notice(m, "inventory_full")  # the drop stays: make room and take it again
            return
        except StoreError:
            world._notice(m, "storage_failed")  # nothing granted, nothing spent: try again
            return
        del self.loot[inst.id][(enemy_id, cid)]
        self.characters[m.pid] = state
        world._notice(m, "picked_up")

    # --- what a player receives -------------------------------------------------------------------------

    def view(self, world: World, m: Member) -> wire.Message | None:
        state = self.characters.get(m.pid)
        if state is None:
            return None
        loot = sorted(enemy for (enemy, cid) in self.loot.get(m.instance or "", {}) if cid == state.id)
        return {"v": 1, "type": "character", "id": state.id, "name": state.name, "items": [list(i) for i in state.items],
                "unlocks": list(state.unlocks), "completed": state.completed, "loot": loot}


def expedition_rules() -> Any:
    """The packaged demonstration's progression rules (mesh_net/expedition/progression.json)."""
    from importlib.resources import files  # noqa: PLC0415

    return json.loads(files("mesh_net").joinpath("expedition", "progression.json").read_text(encoding="utf-8"))


_NAME = re.compile(r"[A-Za-z0-9 _-]{1,24}")


def check_character(msg: wire.Message) -> None:
    """A client's check of a character frame."""
    wire.fields(msg, "character", "id", "name", "items", "unlocks", "completed", "loot")
    if (not isinstance(msg["id"], str) or not re.fullmatch(r"[0-9a-f]{32}", msg["id"])
            or not isinstance(msg["name"], str) or not _NAME.fullmatch(msg["name"])
            or not wire.integer(msg["completed"], 0)
            or type(msg["items"]) is not list or len(msg["items"]) > 16
            or not all(isinstance(r, list) and len(r) == 2 and isinstance(r[0], str) and ITEM_ID.fullmatch(r[0])
                       and wire.integer(r[1], 1, 999) for r in msg["items"])
            or type(msg["unlocks"]) is not list or len(msg["unlocks"]) > 64
            or not all(isinstance(k, str) and UNLOCK_KEY.fullmatch(k) for k in msg["unlocks"])
            or type(msg["loot"]) is not list or len(msg["loot"]) > 32 or not all(isinstance(e, str) for e in msg["loot"])):
        raise wire.Invalid("invalid character")
