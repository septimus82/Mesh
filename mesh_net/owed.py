"""Completions a failing character store still owes (N8, #496). Graphics-free; standard library only.

When the store cannot write a completion (an unlock earned in an expedition), the world may not forget it and may
not pretend it was saved. It is written here first: one small file beside the store, ``<store>.owed``. A new server
reads it before anything else and records what it holds, so a server stopped or killed with completions owed loses
none of them.

* **Append-only, each record durable before anyone is told.** ``owe`` writes one line and ``fsync``s it; ``settle``
  writes that a completion has since been recorded. No record is rewritten in place. A write is done when every
  byte has been taken (a raw write may take fewer than it is given) and the flush has succeeded, not before.
* **A failed append is finished before anything else is written.** None of it counts; at the next write the
  journal reads what it left after the last counted record, writes the rest and flushes, and then it counts
  whole (``Journal._finish``). So a later, shorter record never lands on top of its remains.
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

import errno
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
MAX_LINE = 1024  # longer than any record (a completion key is at most 256 characters)
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
            if used - position > MAX_LINE:
                raise JournalDamaged(f"{path} is damaged: it ends in {used - position} bytes (from byte {position}) "
                                     "that are no record and too long to be one cut short. Nothing was changed.")
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
    """``data`` at byte ``at`` of an existing file: every byte written, then flushed to disk, when this returns.
    (Opened for each write: writes are rare, and a file removed under a running server is found out at the next.)

    A raw write may take fewer bytes than it is given without raising. Each one's count is read, and the next goes
    on from where it stopped; a write that takes nothing (or answers anything but a count of what it was given) is a
    failure, so this ends after at most ``len(data)`` writes. Nothing is flushed, and nothing returns, until the last
    byte is written."""
    with open(path, "r+b", buffering=0) as handle:
        handle.seek(at)
        view = memoryview(data)
        written = 0
        while written < len(view):
            taken = handle.write(view[written:])
            if type(taken) is not int or not 0 < taken <= len(view) - written:
                raise OSError(errno.EIO, f"the write stopped after {written} of {len(view)} bytes")
            written += taken
        os.fsync(handle.fileno())


def _clear(path: Path, start: int, end: int) -> None:
    """Zeros over bytes ``start`` to ``end`` (a last record a crash cut short), flushed when this returns. Last byte
    first, one byte a write: wherever it stops, what is left is still a record cut short followed by zeros, which
    every reader accepts; never zeros followed by data, which none does."""
    with open(path, "r+b", buffering=0) as handle:
        for at in range(end - 1, start - 1, -1):
            handle.seek(at)
            if handle.write(b"\0") != 1:
                raise OSError(errno.EIO, f"the write stopped at byte {at}")
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
        # An append that failed part way: the bytes it was writing. What reached the disk is not known (some of them,
        # all of them unflushed), so nothing else is written until ``_finish`` has dealt with it.
        self.unfinished: bytes | None = None
        try:
            if not path.exists():
                _make(path)
            # (torn: bytes of a last record a crash cut short; that write never completed and nobody was told it had)
            self.entries, self.end, self.torn = read(path)
            if self.torn:
                _clear(path, self.end, self.end + self.torn)
            size = path.stat().st_size
            if size < RESERVED:  # (an older or hand-made file: keep the space now, while the disk takes it)
                _put(path, size, b"\0" * (RESERVED - size))
        except OSError as exc:
            raise JournalError(f"the journal of owed completions {path} cannot be used: {exc}") from exc

    def _count(self, data: bytes) -> None:
        """``data`` (whole records) is on disk and flushed: it counts from here on."""
        for raw in data.splitlines():
            found = _record(raw)
            assert found is not None, "the journal only writes records it can read"
            op, entry = found
            if op == "done":
                self.entries = [e for e in self.entries if e != entry]
            elif entry not in self.entries:
                self.entries.append(entry)
        self.end += len(data)
        self.writes += 1

    def _append(self, data: bytes) -> None:
        """``data`` after the last record: every byte written and flushed when this returns, and counted. On a
        failure nothing is counted and the attempt is remembered: the next write finishes it first (``_finish``)."""
        try:
            if self.fault:
                self.fault("before_write")
            _put(self.path, self.end, data)
        except OSError as exc:
            self.unfinished = data
            raise JournalError(f"the journal of owed completions {self.path} cannot be written: {exc}") from exc
        self._count(data)
        if self.fault:
            self.fault("after_write")

    def _finish(self) -> None:
        """An earlier append failed part way. Before anything else is written, look at what it left after the last
        counted record, write the rest of it, and flush: then it counts, whole.

        What it left can only be the first part of those bytes followed by the zeros kept in advance (possibly all of
        them, if only the flush failed; that is not proof they were not written, and they are not written twice).
        Anything else there is not this server's doing: it is not built on, skipped or erased, and the journal takes
        no more writes. Going on from a prefix keeps the file readable at every step: complete records, then at most
        one cut short. Raises JournalError while it cannot be done; nothing is counted until it is."""
        data = self.unfinished
        if data is None:
            return
        try:
            if self.fault:
                self.fault("before_write")
            with open(self.path, "rb") as handle:
                handle.seek(self.end)
                tail = handle.read()
            there = 0
            while there < min(len(tail), len(data)) and tail[there] == data[there]:
                there += 1
            if tail[there:].strip(b"\0"):
                raise JournalError(
                    f"the journal of owed completions {self.path} holds, after byte {self.end + there}, content that "
                    "is not what this server wrote. Nothing was changed and nothing more is written to it; stop the "
                    "server and look at the file (python -m mesh_net.characters owed STORE)")
            _put(self.path, self.end + there, data[there:])  # (nothing left to write: the flush alone)
        except OSError as exc:
            raise JournalError(f"the journal of owed completions {self.path} cannot be written: {exc}") from exc
        self.unfinished = None
        self._count(data)

    def owe(self, entries: Iterable[Owed]) -> None:
        """Record completions as owed: all written and flushed when this returns (one write), or JournalError and
        none of them counted."""
        self._finish()
        new = [e for e in dict.fromkeys(entries) if e not in self.entries]
        if new:
            self._append(b"".join(_line("owed", e) for e in new))

    def settle(self, entries: Iterable[Owed]) -> None:
        """These completions are recorded in the store: no longer owed. (A settlement lost to a crash is harmless:
        the next server finds the completion owed, and the store refuses to count it twice.)"""
        self._finish()
        done = [e for e in dict.fromkeys(entries) if e in self.entries]
        if done:
            self._append(b"".join(_line("done", e) for e in done))
        if not self.entries and self.end:  # nothing owed: a fresh file, so the space kept in advance is whole again
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
