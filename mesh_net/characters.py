"""Durable multiplayer characters (N8): identity, access keys, inventory, unlocks. Graphics-free.

One SQLite file (standard library) holds every character of one server. WAL journal with ``synchronous=FULL``: a
commit that returns is on disk, and a transaction interrupted by a crash is rolled back when the file is next
opened. Every change is one explicit transaction; the schema's constraints back the identity, quantity and
uniqueness rules (slot and stack limits are checked inside the same transaction).

A store is never created, replaced or repaired implicitly: a missing, corrupt, foreign, read-only or newer file is
refused (:class:`StoreUnavailable`) and its content is not changed. (Opening it does run SQLite's own recovery:
a journal a crashed server left behind, ``-wal``, is folded into the file, which keeps every committed change.)
See docs/networking/n8_persistent_characters.md.

Local administration (the server's owner, on the server's machine)::

    python -m mesh_net.characters new-store STORE
    python -m mesh_net.characters create STORE "Ada" --key-file ada.json   # the key is written there, never printed
    python -m mesh_net.characters list STORE
    python -m mesh_net.characters backup STORE COPY
    python -m mesh_net.characters owed STORE      # completions a failing store still owes (mesh_net.owed)
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import sys
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = 1
APPLICATION_ID = 0x4D534831  # "MSH1": a Mesh character store, not just any SQLite file
NAME = re.compile(r"[A-Za-z0-9_-](?:[A-Za-z0-9 _-]{0,22}[A-Za-z0-9_-])?")
CHARACTER_ID = re.compile(r"[0-9a-f]{32}")
ACCESS_KEY = re.compile(r"[0-9a-f]{64}")
ITEM_ID = re.compile(r"[a-z0-9_]{1,48}")
UNLOCK_KEY = re.compile(r"[a-z0-9_]{1,48}")
MAX_CHARACTERS = 1000
MAX_SLOTS = 16  # distinct items one character can hold
MAX_QUANTITY = 999  # of one item (an item's own max_stack may be lower)
MAX_GRANTS = 8  # items in one claim
MAX_CLAIM = 256  # a claim key: "complete:" + instance id (58) + "/" + enemy id + "/" + rule key (48)

_SCHEMA = """
CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE characters (
    id TEXT PRIMARY KEY CHECK (typeof(id) = 'text' AND length(id) = 32),
    name TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK (typeof(name) = 'text' AND length(name) BETWEEN 1 AND 24),
    key_hash BLOB NOT NULL CHECK (typeof(key_hash) = 'blob' AND length(key_hash) = 32),
    created INTEGER NOT NULL CHECK (typeof(created) = 'integer'),
    completed INTEGER NOT NULL DEFAULT 0 CHECK (typeof(completed) = 'integer' AND completed >= 0)
);
CREATE TABLE inventory (
    character TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    item TEXT NOT NULL CHECK (typeof(item) = 'text' AND length(item) BETWEEN 1 AND 48),
    quantity INTEGER NOT NULL CHECK (typeof(quantity) = 'integer' AND quantity BETWEEN 1 AND 999),
    PRIMARY KEY (character, item)
);
CREATE TABLE unlocks (
    character TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    key TEXT NOT NULL CHECK (typeof(key) = 'text' AND length(key) BETWEEN 1 AND 48),
    granted INTEGER NOT NULL CHECK (typeof(granted) = 'integer'),
    PRIMARY KEY (character, key)
);
CREATE TABLE claims (
    character TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    run TEXT NOT NULL CHECK (typeof(run) = 'text' AND length(run) BETWEEN 1 AND 32),
    claim TEXT NOT NULL CHECK (typeof(claim) = 'text' AND length(claim) BETWEEN 1 AND 256),
    PRIMARY KEY (character, run, claim)
);
"""
_TABLES = {"meta", "characters", "inventory", "unlocks", "claims"}


class StoreUnavailable(Exception):
    """The store cannot be used (missing, corrupt, foreign, newer, read-only). Nothing was changed."""


class StoreError(Exception):
    """A storage operation failed; it was rolled back and nothing it would have changed happened."""


class AccessDenied(Exception):
    """Unknown character, or the access key does not match (one answer for both: no oracle)."""


class NameTaken(ValueError):
    pass


class InventoryFull(Exception):
    """The items do not fit (slots or an item's stack limit); nothing was granted."""


class DuplicateClaim(Exception):
    """This claim was already granted in this run; nothing was granted again."""


@dataclass(frozen=True)
class CharacterState:
    id: str
    name: str
    items: tuple[tuple[str, int], ...]
    unlocks: tuple[str, ...]
    completed: int


def _hash(key: str) -> bytes:
    return hashlib.sha256(bytes.fromhex(key)).digest()


class CharacterStore:
    """One server's characters. Used from one thread (sqlite3 enforces it); every write is a single transaction."""

    def __init__(self, path: str | Path, *, create: bool = False) -> None:
        self.path = Path(path)
        self.stack_limits: Mapping[str, int] = {}  # item id -> most one character may hold (the world sets it)
        self.unlock_keys: frozenset[str] = frozenset()  # the progression keys the world's rules define
        self.fault: Callable[[str], None] | None = None  # tests: called at "before_commit" and "after_commit"
        self.commits = 0
        self.broken = False
        if create and self.path.exists():
            raise StoreUnavailable(f"{self.path} already exists; a store is never replaced")
        if not create and not self.path.is_file():
            raise StoreUnavailable(f"no character store at {self.path} (make one with: python -m mesh_net.characters "
                                   "new-store PATH)")
        try:
            if create:
                self.conn = sqlite3.connect(self.path, isolation_level=None, timeout=1.0)
            else:
                self.conn = sqlite3.connect(f"{self.path.resolve().as_uri()}?mode=rw", uri=True,
                                            isolation_level=None, timeout=1.0)
        except sqlite3.Error as exc:
            raise StoreUnavailable(f"cannot open {self.path}: {exc}") from exc
        try:
            self._prepare(create)
        except StoreUnavailable:
            self.conn.close()
            raise
        except sqlite3.Error as exc:
            self.conn.close()
            if "locked" in str(exc):
                raise StoreUnavailable(f"{self.path} is in use by another server") from exc
            raise StoreUnavailable(f"{self.path} is not a usable character store: {exc}") from exc

    def _prepare(self, create: bool) -> None:
        c = self.conn
        # One server per store: the first write takes an exclusive lock that lasts until close(), so another process
        # (a second server, a stale one) cannot read or write the store meanwhile. That is what keeps "one session
        # per character" true across processes, not only inside one world.
        c.execute("PRAGMA locking_mode=EXCLUSIVE")
        if not create:
            if c.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID:
                raise StoreUnavailable(f"{self.path} is not a Mesh character store")
            if c.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise StoreUnavailable(f"{self.path} is damaged (PRAGMA quick_check); restore a backup")
            tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            row = c.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone() if "meta" in tables else None
            if row is None or not _TABLES <= tables:
                raise StoreUnavailable(f"{self.path} is missing its schema")
            if row[0] != str(SCHEMA_VERSION):
                raise StoreUnavailable(f"{self.path} has schema version {row[0]!r}; this Mesh reads {SCHEMA_VERSION}")
        if c.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower() != "wal":
            raise StoreUnavailable(f"{self.path}: the WAL journal is not available (a network drive?)")
        c.execute("PRAGMA synchronous=FULL")
        c.execute("PRAGMA foreign_keys=ON")
        try:
            c.execute("BEGIN IMMEDIATE")  # (also proves the file is writable before any player relies on it)
            if create:
                c.execute(f"PRAGMA application_id = {APPLICATION_ID}")
                for statement in filter(str.strip, _SCHEMA.split(";")):
                    c.execute(statement)
                c.execute("INSERT INTO meta VALUES ('schema_version', ?)", (str(SCHEMA_VERSION),))
            else:
                c.execute("UPDATE meta SET value = value WHERE key = 'schema_version'")
            c.execute("COMMIT")
        except sqlite3.OperationalError as exc:
            if c.in_transaction:
                c.execute("ROLLBACK")
            if "locked" in str(exc):
                raise StoreUnavailable(f"{self.path} is in use by another server") from exc
            raise StoreUnavailable(f"{self.path} cannot be written: {exc}") from exc

    def close(self) -> None:
        self.conn.close()

    # --- writes: one transaction each ------------------------------------------------------------------

    def _transaction(self, body: Callable[[sqlite3.Connection], object]) -> object:
        c = self.conn
        if self.broken:
            raise StoreError("the store's connection failed earlier; restart the server")
        try:
            c.execute("BEGIN IMMEDIATE")
            result = body(c)
            if self.fault:
                self.fault("before_commit")
            c.execute("COMMIT")
        except (AccessDenied, NameTaken, InventoryFull, DuplicateClaim, ValueError):
            if c.in_transaction:
                c.execute("ROLLBACK")
            raise
        except (sqlite3.Error, OSError) as exc:
            try:
                if c.in_transaction:
                    c.execute("ROLLBACK")
            except sqlite3.Error:
                self.broken = True  # unusable: every later write fails visibly; the journal rolls back on reopen
            raise StoreError(f"storage failed: {exc}") from exc
        self.commits += 1
        if self.fault:
            self.fault("after_commit")
        return result

    def create(self, name: str) -> tuple[str, str]:
        """A new character: (its id, its access key). The key is shown once; only its hash is stored."""
        name = str(name).strip()
        if not NAME.fullmatch(name):
            raise ValueError("a name is 1-24 letters, digits, spaces, _ or -")
        cid, key = secrets.token_hex(16), secrets.token_hex(32)

        def body(c: sqlite3.Connection) -> None:
            if c.execute("SELECT count(*) FROM characters").fetchone()[0] >= MAX_CHARACTERS:
                raise ValueError(f"the store holds its maximum of {MAX_CHARACTERS} characters")
            try:
                c.execute("INSERT INTO characters (id, name, key_hash, created) VALUES (?, ?, ?, ?)",
                          (cid, name, _hash(key), int(time.time())))
            except sqlite3.IntegrityError as exc:
                raise NameTaken(f"there is already a character called {name!r}") from exc

        self._transaction(body)
        return cid, key

    def begin_run(self, run: str, keep: Iterable[str] = ()) -> None:
        """A server run starts: claims of earlier runs name drops and completions that no longer exist; forget them.
        Except the runs in ``keep``: a completion one of them still owes (mesh_net.owed) is recorded under that run,
        and its claims are what stop it being counted twice."""
        runs = sorted({run, *keep})
        marks = ", ".join("?" * len(runs))
        self._transaction(lambda c: c.execute(f"DELETE FROM claims WHERE run NOT IN ({marks})", runs))

    def claim(self, character: str, run: str, claim: str, grants: Iterable[tuple[str, int]]) -> CharacterState:
        """Grant ``grants`` to ``character`` once for ``claim``: all of them or none."""
        grants = list(grants)
        if not grants or len(grants) > MAX_GRANTS or not 0 < len(claim) <= MAX_CLAIM:
            raise ValueError("a claim grants 1-8 items")
        for item, quantity in grants:
            limit = self.stack_limits.get(item)
            if limit is None or not ITEM_ID.fullmatch(item):
                raise ValueError(f"unknown item {item!r}")
            if type(quantity) is not int or not 0 < quantity <= MAX_QUANTITY:
                raise ValueError(f"invalid quantity {quantity!r}")

        def body(c: sqlite3.Connection) -> CharacterState:
            if c.execute("SELECT 1 FROM claims WHERE character = ? AND run = ? AND claim = ?",
                         (character, run, claim)).fetchone():
                raise DuplicateClaim(claim)
            c.execute("INSERT INTO claims VALUES (?, ?, ?)", (character, run, claim))
            held = dict(c.execute("SELECT item, quantity FROM inventory WHERE character = ?", (character,)).fetchall())
            for item, quantity in grants:
                total = held.get(item, 0) + quantity
                if total > min(MAX_QUANTITY, self.stack_limits[item]) or (item not in held and len(held) >= MAX_SLOTS):
                    raise InventoryFull(item)
                held[item] = total
                c.execute("INSERT INTO inventory VALUES (?, ?, ?) ON CONFLICT (character, item) "
                          "DO UPDATE SET quantity = excluded.quantity", (character, item, total))
            return self._state(c, character)  # (read inside the transaction: a commit is never misreported)

        result = self._transaction(body)
        assert isinstance(result, CharacterState)
        return result

    def complete(self, character: str, run: str, completion: str, unlock: str) -> tuple[bool, CharacterState]:
        """An expedition objective done: counted once per ``completion``, and ``unlock`` granted (if not already).
        Returns (whether this unlocked it now, the character)."""
        if unlock not in self.unlock_keys or not UNLOCK_KEY.fullmatch(unlock):
            raise ValueError(f"unknown unlock {unlock!r}")
        claim = f"complete:{completion}"
        if not 0 < len(claim) <= MAX_CLAIM:
            raise ValueError("completion key too long")

        def body(c: sqlite3.Connection) -> tuple[bool, CharacterState]:
            if c.execute("SELECT 1 FROM claims WHERE character = ? AND run = ? AND claim = ?",
                         (character, run, claim)).fetchone():
                raise DuplicateClaim(completion)
            c.execute("INSERT INTO claims VALUES (?, ?, ?)", (character, run, claim))
            c.execute("UPDATE characters SET completed = completed + 1 WHERE id = ?", (character,))
            fresh = c.execute("INSERT OR IGNORE INTO unlocks VALUES (?, ?, ?)",
                              (character, unlock, int(time.time()))).rowcount == 1
            return fresh, self._state(c, character)

        result = self._transaction(body)
        assert isinstance(result, tuple)
        return result

    # --- reads -----------------------------------------------------------------------------------------

    def authenticate(self, character: object, key: object) -> CharacterState:
        if not (isinstance(character, str) and CHARACTER_ID.fullmatch(character)
                and isinstance(key, str) and ACCESS_KEY.fullmatch(key)):
            raise AccessDenied()
        row = self._read("SELECT key_hash FROM characters WHERE id = ?", (character,))
        stored = row[0][0] if row else b"\0" * 32
        if not hmac.compare_digest(stored, _hash(key)) or not row:
            raise AccessDenied()
        return self.load(character)

    def load(self, character: str) -> CharacterState:
        try:
            return self._state(self.conn, character)
        except sqlite3.Error as exc:
            raise StoreError(f"storage read failed: {exc}") from exc

    @staticmethod
    def _state(c: sqlite3.Connection, character: str) -> CharacterState:
        rows = c.execute("SELECT name, completed FROM characters WHERE id = ?", (character,)).fetchall()
        if not rows:
            raise AccessDenied()
        items = c.execute("SELECT item, quantity FROM inventory WHERE character = ? ORDER BY item", (character,))
        unlocks = c.execute("SELECT key FROM unlocks WHERE character = ? ORDER BY key", (character,))
        return CharacterState(character, rows[0][0], tuple((i, q) for i, q in items), tuple(k for k, in unlocks),
                              rows[0][1])

    def characters(self) -> list[CharacterState]:
        return [self.load(cid) for cid, in self._read("SELECT id FROM characters ORDER BY name", ())]

    def _read(self, sql: str, args: tuple) -> list[tuple]:
        try:
            return self.conn.execute(sql, args).fetchall()
        except sqlite3.Error as exc:
            raise StoreError(f"storage read failed: {exc}") from exc

    def backup(self, destination: str | Path) -> None:
        """A consistent copy (SQLite's online backup) to a new file."""
        destination = Path(destination)
        if destination.exists():
            raise FileExistsError(f"{destination} exists; a backup never replaces a file")
        target = sqlite3.connect(destination)
        try:
            self.conn.backup(target)
        finally:
            target.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m mesh_net.characters", description="Local character store administration")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("new-store").add_argument("store")
    p = sub.add_parser("create")
    p.add_argument("store")
    p.add_argument("name")
    p.add_argument("--key-file", required=True, help="where to write the character's id and access key (new file)")
    sub.add_parser("list").add_argument("store")
    p = sub.add_parser("backup")
    p.add_argument("store")
    p.add_argument("copy")
    sub.add_parser("owed", help="list the completions still owed beside the store (it is not opened)").add_argument("store")
    args = parser.parse_args(argv)
    try:
        if args.command == "owed":
            from .owed import describe, journal_path  # noqa: PLC0415  # (owed imports this module)

            entries = describe(args.store)
            for entry in entries:
                print(f"{entry['character']}  {entry['unlock']}  run={entry['run']}  completion={entry['completion']}")
            print(f"{len(entries)} owed in {journal_path(args.store)}; a server opening the store records them")
            return 0
        if args.command == "new-store":
            CharacterStore(args.store, create=True).close()
            print(f"created {args.store}")
            return 0
        store = CharacterStore(args.store)
        try:
            if args.command == "create":
                key_file = Path(args.key_file)
                # The key file is made first (new, private), so a character never exists without its key.
                fd = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    try:
                        cid, key = store.create(args.name)
                    except BaseException:
                        handle.close()
                        key_file.unlink()  # (the empty file this command just made)
                        raise
                    json.dump({"id": cid, "name": args.name.strip(), "key": key}, handle)
                    handle.flush()
                    os.fsync(handle.fileno())
                print(f"created {args.name.strip()!r} ({cid}); access key written to {key_file}")
            elif args.command == "list":
                for state in store.characters():
                    print(f"{state.id}  {state.name}  items={dict(state.items)}  unlocks={list(state.unlocks)}  "
                          f"completed={state.completed}")
            elif args.command == "backup":
                store.backup(args.copy)
                print(f"backed up to {args.copy}")
        finally:
            store.close()
    except (StoreUnavailable, StoreError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
