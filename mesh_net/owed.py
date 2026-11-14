"""Completions a failing character store still owes (N8, #496). Graphics-free; standard library only.

When the store cannot write a completion (an unlock earned in an expedition), the world may not forget it and may
not pretend it was saved. It is written here first: one small file beside the store, ``<store>.owed``. A new server
reads it before anything else and records what it holds, so a server stopped or killed with completions owed loses
none of them.

* **Append-only, each record durable before anyone is told.** ``owe`` writes one line and ``fsync``s it; ``settle``
  writes that a completion has since been recorded. No record is rewritten in place.
* **Space kept in advance.** The file is made ``RESERVED`` bytes long (zeros) when a server first opens the store,
  while the disk still takes writes, and records overwrite that space: a full disk, the likeliest reason for the
  store to fail, does not stop the journal on a file system that writes in place.
* **Replay is safe to repeat.** A record names the character, the *run* that earned it, the completion and the
  unlock: the store's own key for "counted once" (``CharacterStore.complete``). Recording it again, after a crash
  during recovery or a commit whose outcome was never learned, is refused by the store as a duplicate. The store
  keeps the claims of every run named here until its records are settled (``CharacterStore.begin_run(keep=)``).
* **Never repaired or ignored.** A record that does not check out (its checksum, its fields, a settlement of nothing,
  data after the end) refuses the store with where it is; nothing is changed. The one thing tolerated is a last
  record cut short by a crash while it was being written (no line end): that write never completed, nobody was told
  it had, and it is cleared.

A record: ``<crc32 of the JSON, 8 hex digits> <JSON>\\n``, the JSON being
``{"character", "completion", "op": "owed" | "done", "run", "unlock", "v": 1}``.
"""

from __future__ import annotations

import json
import os
import re
import zlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .characters import CHARACTER_ID, MAX_CLAIM, UNLOCK_KEY, StoreUnavailable

RESERVED = 64 * 1024  # bytes kept in advance: about 250 records
SUFFIX = ".owed"
_RUN = re.compile(r"[0-9a-f]{1,32}")
_FIELDS = {"character", "completion", "op", "run", "unlock", "v"}


class JournalError(StoreUnavailable):
    """The journal of owed completions cannot be read or written. Nothing in it was changed."""


class JournalDamaged(JournalError):
    """A record in the journal does not check out. It is never repaired or skipped: the store is refused."""


@dataclass(frozen=True)
class Owed:
    """A completion earned but not yet recorded: what ``CharacterStore.complete`` needs to record it once."""

    character: str
    run: str
    completion: str
    unlock: str


def journal_path(store: str | Path) -> Path:
    return Path(str(store) + SUFFIX)


def _line(op: str, entry: Owed) -> bytes:
    body = json.dumps({"character": entry.character, "completion": entry.completion, "op": op, "run": entry.run,
                       "unlock": entry.unlock, "v": 1}, sort_keys=True, separators=(",", ":")).encode("ascii")
    return b"%08x " % zlib.crc32(body) + body + b"\n"


def _record(line: bytes) -> tuple[str, Owed] | None:
    """(op, entry) of one complete line; None if it does not check out."""
    try:
        if len(line) < 10 or line[8:9] != b" " or int(line[:8], 16) != zlib.crc32(line[9:]):
            return None
        data = json.loads(line[9:].decode("ascii"))
    except (ValueError, UnicodeDecodeError):
        return None
    if (not isinstance(data, dict) or set(data) != _FIELDS or data["v"] != 1 or data["op"] not in ("owed", "done")
            or not all(isinstance(data[k], str) for k in ("character", "completion", "run", "unlock"))
            or not CHARACTER_ID.fullmatch(data["character"]) or not _RUN.fullmatch(data["run"])
            or not UNLOCK_KEY.fullmatch(data["unlock"]) or not 0 < len(data["completion"]) <= MAX_CLAIM):
        return None
    return data["op"], Owed(data["character"], data["run"], data["completion"], data["unlock"])


def read(path: Path) -> tuple[list[Owed], int, int]:
    """What the journal file says: (completions still owed, oldest first; where its records end; the length of a last
    record cut short, 0 if none). Raises JournalDamaged for anything else that does not check out."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise JournalError(f"the journal of owed completions {path} cannot be read: {exc}") from exc
    used = data.find(b"\0")
    used = len(data) if used < 0 else used
    if data[used:].strip(b"\0"):
        raise JournalDamaged(f"{path} is damaged: there is data after its end (byte {used}). Nothing was changed.")
    owed: dict[Owed, None] = {}
    position = 0
    while position < used:
        end = data.find(b"\n", position, used)
        if end < 0:  # the last record has no line end: a write a crash cut short
            return list(owed), position, used - position
        found = _record(data[position:end])
        if found is None:
            raise JournalDamaged(f"{path} is damaged: the record at byte {position} does not check out. Nothing was "
                                 "changed; the completions it holds are not lost while the file is kept.")
        op, entry = found
        if op == "owed":
            owed[entry] = None
        elif entry in owed:
            del owed[entry]
        else:
            raise JournalDamaged(f"{path} is damaged: the record at byte {position} settles a completion it never "
                                 "recorded as owed. Nothing was changed.")
        position = end + 1
    return list(owed), used, 0


def _put(path: Path, at: int, data: bytes) -> None:
    """``data`` at byte ``at`` of an existing file, on disk when this returns. (Opened for each write: writes are
    rare, and a file removed under a running server is found out at the next one.)"""
    with open(path, "r+b", buffering=0) as handle:
        handle.seek(at)
        handle.write(data)
        os.fsync(handle.fileno())


def _make(path: Path) -> None:
    """A new, empty journal with its space kept: written beside the store, then moved into place whole."""
    fresh = path.with_name(path.name + ".new")
    with open(fresh, "wb") as handle:
        handle.write(b"\0" * RESERVED)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(fresh, path)
    if os.name != "nt":  # make the rename durable where the folder itself must be flushed (Windows cannot open one)
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


class Journal:
    """The owed completions of one store, used by the one server that holds the store (its exclusive lock)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.fault: Callable[[str], None] | None = None  # tests: called at "before_write" and "after_write"
        self.writes = 0
        try:
            if not path.exists():
                _make(path)
            # (torn: bytes of a last record a crash cut short; that write never completed and nobody was told it had)
            self.entries, self.end, self.torn = read(path)
            if self.torn:
                _put(path, self.end, b"\0" * self.torn)
            size = path.stat().st_size
            if size < RESERVED:  # (an older or hand-made file: keep the space now, while the disk takes it)
                _put(path, size, b"\0" * (RESERVED - size))
        except OSError as exc:
            raise JournalError(f"the journal of owed completions {path} cannot be used: {exc}") from exc

    def _append(self, data: bytes) -> None:
        """``data`` after the last record, durable when this returns. On a failure nothing is counted as written: the
        next write starts at the same place."""
        try:
            if self.fault:
                self.fault("before_write")
            _put(self.path, self.end, data)
        except OSError as exc:
            raise JournalError(f"the journal of owed completions {self.path} cannot be written: {exc}") from exc
        self.end += len(data)
        self.writes += 1
        if self.fault:
            self.fault("after_write")

    def owe(self, entries: Iterable[Owed]) -> None:
        """Record completions as owed: all durable when this returns (one write), or JournalError and none counted."""
        new = [e for e in dict.fromkeys(entries) if e not in self.entries]
        if new:
            self._append(b"".join(_line("owed", e) for e in new))
            self.entries.extend(new)

    def settle(self, entries: Iterable[Owed]) -> None:
        """These completions are recorded in the store: no longer owed. (A settlement lost to a crash is harmless:
        the next server finds the completion owed, and the store refuses to count it twice.)"""
        done = [e for e in dict.fromkeys(entries) if e in self.entries]
        if not done:
            return
        self._append(b"".join(_line("done", e) for e in done))
        self.entries = [e for e in self.entries if e not in done]
        if not self.entries:  # nothing owed: a fresh file, so the space kept in advance is whole again
            try:
                _make(self.path)
                self.end = 0
            except OSError:
                pass  # (no room for a fresh file now: the old one, complete and correct, goes on being appended to)


def describe(store: str | Path) -> list[dict[str, Any]]:
    """The completions still owed beside ``store``, for the owner (``python -m mesh_net.characters owed STORE``)."""
    path = journal_path(store)
    if not path.exists():
        return []
    return [{"character": e.character, "run": e.run, "completion": e.completion, "unlock": e.unlock}
            for e in read(path)[0]]
