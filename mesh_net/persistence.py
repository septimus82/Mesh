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
import logging
import math
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from engine.interaction import DEFAULT_INTERACT_MAX_DIST

from . import protocol as wire
from .characters import (
    ITEM_ID,
    MAX_CLAIM,
    MAX_GRANTS,
    MAX_QUANTITY,
    UNLOCK_KEY,
    AccessDenied,
    CharacterState,
    CharacterStore,
    DuplicateClaim,
    InventoryFull,
    StoreError,
)
from .owed import Journal, JournalError, Owed, journal_path
from .scene_room import Unsupported, roll_drops

if TYPE_CHECKING:
    from .world import Instance, Member, RoomDef, World

logger = logging.getLogger(__name__)
RECORDED_PER_TICK = 8  # owed completions recorded in one tick once the store works again (each is a commit)
MAX_RULES = 64
CLAIM_ROOM = 60  # the longest room-instance id part of a claim key ("<key>:<n>/")
# "unlock_owed": earned, not yet recorded, kept in the journal (mesh_net.owed) and recorded when the store works again,
# also after a restart. "unlock_not_kept": the journal failed too; held only in this server's memory.
NOTICES = ("picked_up", "inventory_full", "storage_failed", "unlocked", "unlock_owed", "unlock_not_kept")


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
    if len(data["unlocks"]) > MAX_RULES:
        raise Unsupported(f"at most {MAX_RULES} unlocks (a character sheet lists them all)")
    for key, rule in sorted(data["unlocks"].items()):
        if (not UNLOCK_KEY.fullmatch(str(key)) or not isinstance(rule, dict) or set(rule) != {"label", "room", "defeat"}
                or not all(isinstance(rule[k], str) for k in rule)):
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
            if len(enemy) > MAX_CLAIM - CLAIM_ROOM - 60:  # (room for "complete:", the instance, the enemy and a rule)
                raise Unsupported(f"enemy id '{enemy[:40]}...' is too long to claim loot from")
            for drop in (table or {}).get("drops") or []:
                item = drop.get("item_id") if isinstance(drop, dict) else None
                if item and str(item).strip() not in limits:
                    raise Unsupported(f"enemy '{enemy}' drops '{item}', which assets/data/items.json does not define")
                if item:
                    try:
                        low = int(drop.get("min_quantity", drop.get("quantity", 1)) or 1)
                        high = max(low, int(drop.get("max_quantity", low) or low))
                    except (TypeError, ValueError):
                        low = high = 0
                    if not 0 < low <= high <= MAX_QUANTITY:  # (roll_drops' reading of a quantity)
                        raise Unsupported(f"enemy '{enemy}' drops '{item}' in quantities a character cannot hold")
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
    sent: dict[int, wire.Message] = field(default_factory=dict)
    # Completions earned that the store has not recorded, oldest first (#496). Each is in ``journal`` (durable: a
    # server stopped or killed now records it at its next start) unless it is in ``unkept``.
    owed: list[Owed] = field(default_factory=list)
    journal: Journal | None = None
    unkept: set[Owed] = field(default_factory=set)  # the journal failed too: these exist only in this process
    refused: dict[Owed, str] = field(default_factory=dict)  # owed, and refused by the store for a reason of its own
    recovered: int = 0  # owed by earlier runs and recorded when this one started

    @classmethod
    def open(cls, root: Path, defs: dict[str, RoomDef], store: CharacterStore, rules: Any) -> Progress:
        """Raises mesh_net.owed.JournalError (a StoreUnavailable) if the journal of owed completions cannot be used:
        a server never starts without knowing what an earlier run still owes."""
        progress = cls(store, load_rules(rules, defs))
        store.stack_limits = item_limits(root, defs)
        store.unlock_keys = frozenset(r.key for r in progress.rules)
        progress.journal = journal = Journal(journal_path(store.path))
        progress.owed = list(journal.entries)
        if journal.torn:
            logger.warning("[Mesh][Net] %s: its last record was cut short while being written (%d bytes); that write "
                           "never completed and was cleared", journal.path.name, journal.torn)
        # (An owed completion is recorded under the run that earned it: that run's claims must outlive this start.)
        store.begin_run(progress.run, keep={e.run for e in progress.owed})
        if progress.owed:  # before anyone joins: what earlier runs owe
            before = len(progress.owed)
            progress._record(None, limit=None)
            progress.recovered = before - len(progress.owed)
            logger.warning("[Mesh][Net] %d completions owed by earlier runs: %d recorded now, %d still owed",
                           before, progress.recovered, len(progress.owed))
        return progress

    @property
    def accepting(self) -> bool:
        """Whether a new expedition may start. Not while the store is failing: a completion is owed that the store
        has not refused for a reason of its own, or its connection is broken. Expeditions under way go on (what they
        earn is owed too); no new one starts until everything owed is recorded."""
        return not self.store.broken and all(e in self.refused for e in self.owed)

    def close(self) -> None:
        """The server stops. What the journal holds is recorded by the next start; what it could not take is lost,
        and said so."""
        for entry in self.owed:
            if entry in self.unkept:
                logger.error("[Mesh][Net] LOST: unlock %s earned by character %s was never recorded (the store and "
                             "the journal of owed completions both failed)", entry.unlock, entry.character)

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
        if self.owed:  # completions a failing store owes (tried again each tick)
            self._record(world)
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
        owed = []
        for rule in self.rules:
            if rule.room == inst.key and rule.defeat == enemy_id:
                for m in present:  # (one completion per rule: two rules on one enemy are two completions)
                    entry = self._complete(world, self.characters[m.pid].id, f"{inst.id}/{enemy_id}/{rule.key}", rule.key)
                    if entry is not None:
                        owed.append(entry)
        if owed:  # the store did not take them: owed from here on, and kept before anyone is told
            self.owed.extend(owed)
            self._keep(world, owed)

    def _complete(self, world: World, cid: str, completion: str, key: str) -> Owed | None:
        """Record a completion just earned. Returns it if the store did not take it (it is then owed)."""
        pid = self.owner.get(cid)
        try:
            fresh, state = self.store.complete(cid, self.run, completion, key)
        except DuplicateClaim:
            return None
        except (StoreError, ValueError) as exc:
            entry = Owed(cid, self.run, completion, key)
            if isinstance(exc, ValueError):  # (not a storage failure; the rules are checked at load, so not expected)
                self.refused[entry] = str(exc)
            logger.warning("[Mesh][Net] unlock %s earned by character %s not recorded: %s", key, cid, exc)
            return entry
        if pid is not None:
            self.characters[pid] = state
            if fresh:
                world._notice(world.members[pid], "unlocked")
        return None

    def _keep(self, world: World | None, entries: list[Owed]) -> None:
        """Write owed completions to the journal, then tell their characters what is true: kept ("unlock_owed"), or,
        if the journal failed too, held only in this server's memory ("unlock_not_kept")."""
        try:
            if self.journal is None:
                raise JournalError("this world has no journal of owed completions")
            self.journal.owe(entries)
        except JournalError as exc:
            told = [e for e in entries if e not in self.unkept]  # (said once, not on every later try)
            self.unkept.update(entries)
            for entry in told:
                logger.error("[Mesh][Net] unlock %s owed to character %s is held in memory only (%s): it is lost if "
                             "the server stops before its storage works again", entry.unlock, entry.character, exc)
            code = "unlock_not_kept"
        else:
            self.unkept.difference_update(entries)
            told, code = entries, "unlock_owed"
        if world is not None:
            for entry in told:
                pid = self.owner.get(entry.character)
                if pid is not None:
                    world._notice(world.members[pid], code)

    def _record(self, world: World | None, limit: int | None = RECORDED_PER_TICK) -> None:
        """Record what is owed, oldest first, until the store fails again (it is still down: the rest wait too) or
        ``limit`` are done. Each is recorded under the run that earned it, so the store counts it once however often
        this is tried, in this process or after any number of restarts."""
        settled: list[Owed] = []
        for entry in [e for e in self.owed if e not in self.refused][:limit]:
            pid = self.owner.get(entry.character)
            state: CharacterState | None
            try:
                fresh, state = self.store.complete(entry.character, entry.run, entry.completion, entry.unlock)
            except DuplicateClaim:  # recorded already: by a commit whose outcome was never learned, or an earlier try
                fresh, state = False, None
                if pid is not None:
                    try:
                        state = self.store.load(entry.character)
                        fresh = entry.unlock in state.unlocks and entry.unlock not in self.characters[pid].unlocks
                    except (StoreError, AccessDenied):
                        state = None  # (the sheet is read again at the character's next commit or join)
            except StoreError:
                break
            except (ValueError, AccessDenied) as exc:
                # Not a storage failure: as things stand the store will never take it (the rules no longer define the
                # unlock, the character is gone). It stays in the journal, named here and by the owed command.
                self.refused[entry] = str(exc) or type(exc).__name__
                logger.error("[Mesh][Net] unlock %s owed to character %s cannot be recorded (%s); it stays in the "
                             "journal of owed completions", entry.unlock, entry.character, self.refused[entry])
                continue
            settled.append(entry)
            if pid is not None and state is not None:
                self.characters[pid] = state
                if fresh and world is not None:
                    world._notice(world.members[pid], "unlocked")
        if settled:
            self.owed = [e for e in self.owed if e not in settled]
            kept = [e for e in settled if e not in self.unkept]
            self.unkept.difference_update(settled)
            try:
                if self.journal is not None:
                    self.journal.settle(kept)
            except JournalError as exc:  # recorded all the same; the next start finds them owed and settles them
                logger.warning("[Mesh][Net] %d owed completions recorded, the journal not updated: %s", len(kept), exc)
        if self.unkept:  # what the journal could not take: try again, so that a stop loses nothing
            self._keep(world, [e for e in self.owed if e in self.unkept])

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
        except (StoreError, ValueError) as exc:  # (a grant the store refuses never stops the world)
            logger.warning("[Mesh][Net] loot for character %s not recorded: %s", cid, exc)
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
