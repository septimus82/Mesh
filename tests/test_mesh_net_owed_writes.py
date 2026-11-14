"""The journal of owed completions never calls a write done that was not (#510 review: short writes).

A raw file write may take fewer bytes than it was given, or none, without raising. The journal used to ignore how
many it took: it then counted an incomplete record as written, and the player was told their unlock was kept when a
restart would discard it. And a failed append left its bytes behind, where the next, shorter, write turned them into
a record that does not check out: a journal the next server refuses.

Every case here is driven by a scripted file (``Scripted``) and a scripted ``fsync``: no disk has to fill. The
checks read the journal's bytes, the entries decoded from them, and what the character store holds.
"""

from __future__ import annotations

import asyncio
import builtins
import os
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from mesh_net import owed
from mesh_net.characters import CharacterStore
from mesh_net.owed import Journal, JournalError, Owed
from mesh_net.world import expedition_files
from tests.net_owed_server import Client, ServerProcess
from tests.test_mesh_net_characters import UNLOCK, P, creds, pworld, to_layer_2
from tests.test_mesh_net_world import GUARDIAN, R2, kill

pytestmark = pytest.mark.integration
GUARDIAN_AT = (480.0, 256.0)
A = Owed("a" * 32, "ab12", "room:1/guardian/k", UNLOCK)
B = Owed("b" * 32, "ab12", "room:1/guardian/k", UNLOCK)
C = Owed("c" * 32, "ab12", "room:22/a_much_longer_guardian_name_than_the_others_have/k", UNLOCK)
SHORT = Owed("d" * 32, "a", "r:1/g/k", "k")  # the shortest record there is: shorter than what a failed write leaves


class Scripted:
    """The journal's file, with what each ``write`` and each ``fsync`` does scripted (a list, consumed in order;
    when it is used up everything works): for a write, a number takes only that many bytes (0: none), ``"all"`` takes
    them all, an exception is raised; for an fsync, ``None`` works and an exception is raised. ``log`` is what
    happened, in order."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, writes: list[Any] | None = None,
                 fsyncs: list[Any] | None = None) -> None:
        self.writes, self.fsyncs, self.log = list(writes or []), list(fsyncs or []), []
        script = self
        real_fsync = os.fsync

        class File:
            def __init__(self, real: Any) -> None:
                self.real = real

            def write(self, data: Any) -> int:
                step = script.writes.pop(0) if script.writes else "all"
                if isinstance(step, BaseException):
                    script.log.append(("write fails", len(data)))
                    raise step
                taken = len(data) if step == "all" else min(int(step), len(data))
                self.real.write(bytes(data[:taken]))
                script.log.append(("write", taken, len(data)))
                return taken

            def __enter__(self) -> File:
                return self

            def __exit__(self, *exc: Any) -> None:
                self.real.close()

            def __getattr__(self, name: str) -> Any:
                return getattr(self.real, name)

        def opened(path: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
            real = builtins.open(path, mode, *args, **kwargs)
            return File(real) if mode == "r+b" else real

        def fsync(fd: int) -> None:
            step = script.fsyncs.pop(0) if script.fsyncs else None
            if isinstance(step, BaseException):
                script.log.append(("fsync fails",))
                raise step
            real_fsync(fd)
            script.log.append(("fsync",))

        monkeypatch.setattr(owed, "open", opened, raising=False)
        monkeypatch.setattr(owed.os, "fsync", fsync)


def on_disk(path: Path) -> list[Owed]:
    """The completions the journal file holds as owed, decoded from its bytes (raises if it is damaged)."""
    return owed.read(path)[0]


def used(path: Path) -> bytes:
    """The journal's bytes up to the zeros kept in advance."""
    return path.read_bytes().rstrip(b"\0")


def line(*entries: Owed, op: str = "owed") -> bytes:
    return b"".join(owed._line(op, e) for e in entries)


@pytest.fixture
def journal(tmp_path: Path) -> Journal:
    """A journal that already holds one durable entry (A)."""
    made = Journal(tmp_path / "characters.db.owed")
    made.owe([A])
    return made


# --- a write that takes fewer bytes than it was given ----------------------------------------------------


@pytest.mark.parametrize("writes", [[40, "all"], [1, 1, 1, 60, 3, "all"], [7] * 40], ids=["one", "several", "many"])
def test_short_writes_are_finished_before_the_record_counts(journal, monkeypatch, writes):
    script = Scripted(monkeypatch, writes)
    journal.owe([B])
    # every byte is on disk, in order, and flushed once, after the last of them
    assert used(journal.path) == line(A, B) and on_disk(journal.path) == [A, B] == journal.entries
    assert script.log[-1] == ("fsync",) and [e for e in script.log if e[0] == "fsync"] == [("fsync",)]
    assert sum(e[1] for e in script.log if e[0] == "write") == len(line(B)) == journal.end - len(line(A))
    assert Journal(journal.path).entries == [A, B]  # (and a new server reads the same)


@pytest.mark.parametrize("writes", [[0], [40, 0], [40, -1]], ids=["none taken", "some then none", "a negative count"])
def test_a_write_that_makes_no_progress_fails_and_never_spins(journal, monkeypatch, writes):
    script = Scripted(monkeypatch, writes)
    with pytest.raises(JournalError, match="cannot be written"):
        journal.owe([B])
    assert journal.entries == [A] and journal.end == len(line(A)), "nothing counted"
    assert len([e for e in script.log if e[0] == "write"]) == len(writes), "it stopped at the write that took nothing"
    assert ("fsync",) not in script.log, "an incomplete write is never flushed as if it were whole"
    assert on_disk(journal.path) == [A]  # the durable entry is untouched; B is not there to be believed


def test_a_short_write_followed_by_an_error_fails_and_counts_nothing(journal, monkeypatch):
    Scripted(monkeypatch, [40, OSError(5, "Input/output error")])
    with pytest.raises(JournalError, match="cannot be written"):
        journal.owe([B])
    assert journal.entries == [A] and on_disk(journal.path) == [A]
    assert used(journal.path) == line(A) + line(B)[:40]  # (the 40 bytes are there, a record cut short)


def test_a_short_write_in_a_batch_of_completions_is_finished_too(journal, monkeypatch):
    whole = line(B, C)
    Scripted(monkeypatch, [len(line(B)) + 9, "all"])  # the first record and a little of the second, then the rest
    journal.owe([B, C])
    assert used(journal.path) == line(A) + whole and on_disk(journal.path) == [A, B, C] == journal.entries


# --- after a failed append: what is on disk is reconciled before anything else is written ---------------------


def test_a_shorter_write_after_a_failed_one_does_not_damage_the_journal(journal, monkeypatch):
    """The sequence the review asked about: valid entries; an append that writes part of a batch and fails; the
    journal's position unchanged; then a shorter record written at that same place."""
    script = Scripted(monkeypatch, [len(line(C)) + 30, OSError(28, "No space left on device")])
    with pytest.raises(JournalError):
        journal.owe([C, B])  # C whole and 30 bytes of B reach the disk, then the write fails
    assert journal.entries == [A]
    journal.owe([SHORT])  # (shorter than what the failed write left behind)
    # Not damaged: a new server reads it. Nothing that was durable is gone. The failed append was finished first
    # (C, which had reached the disk whole, is never skipped or erased; the rest of B was written), flushed, and
    # only then counted; SHORT was written after it, not over it.
    assert on_disk(journal.path) == [A, C, B, SHORT] == journal.entries == Journal(journal.path).entries
    assert used(journal.path) == line(A, C, B, SHORT)
    assert script.log.count(("fsync",)) == 2  # one for the finished append, one for SHORT


def test_a_whole_write_whose_flush_failed_is_not_taken_for_unwritten(journal, monkeypatch):
    Scripted(monkeypatch, fsyncs=[OSError(5, "Input/output error")])
    with pytest.raises(JournalError):
        journal.owe([C])  # every byte written; the flush failed: its durability is not known
    assert journal.entries == [A], "not counted: nobody is told it is kept on the strength of this"
    assert used(journal.path) == line(A, C)  # (it is on disk all the same)
    journal.owe([SHORT])  # the next write first finds out what is there, flushes it, and keeps it
    assert on_disk(journal.path) == [A, C, SHORT] == journal.entries
    journal.owe([C])  # asking again for what is already kept writes nothing
    assert used(journal.path) == line(A, C, SHORT)


def test_the_same_entries_tried_again_after_a_failed_write_are_written_once(journal, monkeypatch):
    Scripted(monkeypatch, [len(line(B)) + 9, OSError(28, "No space left on device")])
    with pytest.raises(JournalError):
        journal.owe([B, C])
    journal.owe([B, C])  # the retry: B is already there whole, only C is written
    assert used(journal.path) == line(A, B, C) and on_disk(journal.path) == [A, B, C] == journal.entries


def test_a_failed_settlement_is_reconciled_and_nothing_owed_is_lost(journal, monkeypatch):
    journal.owe([B, C])
    Scripted(monkeypatch, [len(line(A, op="done")) + 5, OSError(5, "Input/output error")])
    with pytest.raises(JournalError):
        journal.settle([A, B])  # "A is recorded" reaches the disk whole, 5 bytes of "B is recorded", then it fails
    assert journal.entries == [A, B, C]
    assert on_disk(journal.path) == [B, C]  # (what a new server would read now: A settled, B and C still owed)
    journal.settle([B])  # reconciled first (A's settlement kept, the 5 bytes cleared), then B's written
    assert on_disk(journal.path) == [C] == journal.entries and used(journal.path) == line(A, B, C) + line(A, B, op="done")
    assert Journal(journal.path).entries == [C]


def test_a_journal_that_cannot_be_reconciled_takes_no_more_writes(journal, monkeypatch):
    Scripted(monkeypatch, [30, OSError(5, "Input/output error")], fsyncs=[OSError(5, "Input/output error")] * 2)
    with pytest.raises(JournalError):
        journal.owe([B])
    for _ in range(2):  # the flush still fails: B is never counted, and nothing is written after it
        with pytest.raises(JournalError, match="cannot be written"):
            journal.owe([SHORT])
        assert journal.entries == [A] and journal.end == len(line(A))
        assert used(journal.path) == line(A, B)  # (B's bytes are there, unflushed: not yet to be believed)
    journal.owe([SHORT])  # the disk works again: B flushed and counted, then SHORT
    assert on_disk(journal.path) == [A, B, SHORT] == journal.entries and used(journal.path) == line(A, B, SHORT)


def test_content_that_is_not_what_was_written_is_never_built_on_or_erased(journal, monkeypatch):
    Scripted(monkeypatch, [30, OSError(5, "Input/output error")])
    with pytest.raises(JournalError):
        journal.owe([B])
    with builtins.open(journal.path, "r+b") as handle:  # something else wrote a record here meanwhile
        handle.seek(journal.end)
        handle.write(line(C))
    before = journal.path.read_bytes()
    with pytest.raises(JournalError, match="not what this server wrote"):
        journal.owe([SHORT])
    assert journal.path.read_bytes() == before, "left exactly as found: not skipped, not erased, not written past"
    assert on_disk(journal.path) == [A, C]  # (and a new server reads it for what it is)


# --- what the player is told, and what a restart finds -------------------------------------------------------


@pytest.fixture(scope="module")
def files():
    return expedition_files()


def failing(point: str) -> None:
    if point == "before_commit":
        raise sqlite3.OperationalError("disk I/O error")


def _owing_world(files, tmp_path, monkeypatch, *names):
    store = CharacterStore(tmp_path / "characters.db", create=True)
    people = creds(store, *names)
    d = P(pworld(files, store))
    pids = [d.enter(c) for c in people]
    for other in pids[1:]:
        d.party(pids[0], other)
    if len(pids) == 1:
        d.ask(pids[0], "create")
    to_layer_2(d, *pids)
    store.fault = failing
    return store, d, people, pids


def test_the_player_is_told_kept_only_after_every_byte_is_written_and_flushed(files, tmp_path, monkeypatch):
    store, d, (ada,), (a,) = _owing_world(files, tmp_path, monkeypatch, "Ada")
    try:
        script = Scripted(monkeypatch, [25, 25, "all"])
        notice = d.w._notice
        monkeypatch.setattr(d.w, "_notice", lambda m, code: (script.log.append(("notice", code)), notice(m, code))[1])
        kill(d, a, GUARDIAN_AT, 2)
        path = owed.journal_path(store.path)
        events = [e[0] if e[0] != "notice" else e for e in script.log]
        assert events == ["write", "write", "write", "fsync", ("notice", "unlock_owed")]
        assert len(on_disk(path)) == 1 and d.notices(a) == ["unlock_owed"]
    finally:
        store.close()


def test_a_write_that_never_completes_is_not_called_kept_and_a_restart_agrees(files, tmp_path, monkeypatch):
    """The review's finding, end to end: the journal write takes part of the record and then no more."""
    store, d, (ada,), (a,) = _owing_world(files, tmp_path, monkeypatch, "Ada")
    path = store.path
    try:
        Scripted(monkeypatch, [60, 0] + [0] * 50)  # (and it goes on taking nothing in the ticks that follow)
        kill(d, a, GUARDIAN_AT, 2)
        told = d.notices(a)
        kept_on_disk = on_disk(owed.journal_path(path))
    finally:
        store.close()
    # What the player was told and what a restart finds must agree: here, not kept.
    assert told == ["unlock_not_kept"] and kept_on_disk == []
    monkeypatch.undo()
    store = CharacterStore(path)
    try:
        world = pworld(files, store)  # the next server: its journal is sound, and holds nothing for Ada
        assert world.progress.recovered == 0 and store.load(ada["id"]).unlocks == () and world.progress.accepting
    finally:
        store.close()


def test_kept_after_a_failed_then_retried_write_is_recorded_exactly_once(files, tmp_path, monkeypatch):
    store, d, (ada, bo), (a, b) = _owing_world(files, tmp_path, monkeypatch, "Ada", "Bo")
    path = store.path
    try:
        probe = Journal(tmp_path / "probe.owed")  # (only to learn how long one record is here)
        probe.owe([Owed(ada["id"], d.w.progress.run, f"{d.m(a).instance}/{GUARDIAN}/{UNLOCK}", UNLOCK)])
        Scripted(monkeypatch, [probe.end + 20, OSError(28, "No space left on device")])
        kill(d, a, GUARDIAN_AT, 2)  # Ada's record whole and some of Bo's, the write fails; later ticks try again
        # First both were told "not kept" (the batch failed); the next tick reconciled, wrote Bo's, told both "kept".
        assert d.notices(a) == ["unlock_not_kept", "unlock_owed"] and d.notices(b) == ["unlock_not_kept", "unlock_owed"]
        assert [e.character for e in on_disk(owed.journal_path(path))] == [ada["id"], bo["id"]]
        assert len(used(owed.journal_path(path)).splitlines()) == 2, "each written once, nothing left over"
    finally:
        store.close()
    monkeypatch.undo()
    for _ in range(2):  # a restart records each once; another changes nothing
        store = CharacterStore(path)
        try:
            pworld(files, store)
            assert [store.load(c["id"]).completed for c in (ada, bo)] == [1, 1]
            assert all(store.load(c["id"]).unlocks == (UNLOCK,) for c in (ada, bo))
            assert on_disk(owed.journal_path(path)) == []
        finally:
            store.close()


def test_a_server_killed_in_the_middle_of_an_append_restarts_on_a_sound_journal(tmp_path):
    """A real process dies while writing a batch of two: the first record whole, the second cut short. Nobody had
    been told anything. The next server keeps the whole record (it counts once), clears the cut one, and starts."""
    path = tmp_path / "characters.db"
    store = CharacterStore(path, create=True)
    try:
        ada, bo = creds(store, "Ada", "Bo")
    finally:
        store.close()
    ids = [ada["id"], bo["id"]]

    async def play() -> int:
        server = ServerProcess(path)
        try:
            clients = [await Client.join(server.port, c) for c in (ada, bo)]
            for client in clients:
                await client.until(lambda c: c.room and c.sheet is not None)
            assert (await asyncio.to_thread(server.ask, op="to_guardian", characters=ids))["rooms"] == [R2, R2]
            await asyncio.to_thread(server.ask, op="fault", store="fail", journal="torn:0.6")
            code = await asyncio.to_thread(server.dies, op="kill_guardian", character=ids[0])
            for client in clients:
                await client.until(lambda c: c.gone)
                assert not {"unlock_owed", "unlocked"} & set(client.notices)  # nothing had been claimed
                await client.close()
            return code
        finally:
            server.kill()

    assert asyncio.run(play()) == 9
    raw = used(owed.journal_path(path))
    assert raw.count(b"\n") == 1 and not raw.endswith(b"\n"), "one whole record, then one cut short"
    assert owed.read(owed.journal_path(path))[2] > 0 and [e.character for e in on_disk(owed.journal_path(path))] == ids[:1]

    for start in range(2):
        server = ServerProcess(path)
        try:
            state = server.ask(op="state")
            assert state["recovered"] == (1 if start == 0 else 0) and state["owed"] == 0 and state["accepting"]
        finally:
            server.kill()
        check = CharacterStore(path)
        try:
            assert [check.load(c).completed for c in ids] == [1, 0]  # the whole record counted once; the cut one never
            assert check.load(ids[0]).unlocks == (UNLOCK,) and check.load(ids[1]).unlocks == ()
        finally:
            check.close()
        assert used(owed.journal_path(path)) == b""  # sound, and empty again


def test_recorded_by_the_store_before_the_journal_worked_again_leaves_nothing_behind(files, tmp_path, monkeypatch):
    """The journal write fails part way; before it is tried again the store works and records the completion. The
    journal's unfinished write is finished and settled in the same tick: nothing stale for a restart to replay."""
    store, d, (ada,), (a,) = _owing_world(files, tmp_path, monkeypatch, "Ada")
    path = store.path
    try:
        script = Scripted(monkeypatch, [50] + [OSError(5, "Input/output error")] * 100)
        kill(d, a, GUARDIAN_AT, 2)  # the journal write takes 50 bytes and fails, and fails in every tick after
        assert d.notices(a) == ["unlock_not_kept"] and on_disk(owed.journal_path(path)) == []
        script.writes.clear()  # the disk works again, and so does the store, in the same tick
        store.fault = None
        d.step()
        assert store.load(ada["id"]).completed == 1 and d.w.progress.owed == [] and not d.w.progress.unkept
        assert "unlocked" in d.notices(a)
        assert on_disk(owed.journal_path(path)) == [] and used(owed.journal_path(path)) == b""
        assert d.w.progress.journal.entries == [] and d.w.progress.journal.unfinished is None
    finally:
        store.close()
    monkeypatch.undo()
    store = CharacterStore(path)
    try:
        world = pworld(files, store)
        assert world.progress.recovered == 0 and store.load(ada["id"]).completed == 1
    finally:
        store.close()


# --- a record cut short, found by a new server ---------------------------------------------------------------


def _cut_short(path: Path) -> tuple[int, int]:
    """A journal holding A, then the first 70 bytes of B (a crash during that write): (where A ends, 70)."""
    Journal(path).owe([A])
    with builtins.open(path, "r+b") as handle:
        handle.seek(len(line(A)))
        handle.write(line(B)[:70])
    return len(line(A)), 70


def test_clearing_a_record_cut_short_can_stop_anywhere_and_the_journal_stays_readable(tmp_path, monkeypatch):
    path = tmp_path / "characters.db.owed"
    end, torn = _cut_short(path)
    for stop_after in (0, 1, 30):  # the clearing itself is interrupted, at different points
        with pytest.MonkeyPatch.context() as patch:
            Scripted(patch, ["all"] * stop_after + [OSError(5, "Input/output error")])
            with pytest.raises(JournalError, match="cannot be used"):
                Journal(path)
        left = used(path)
        # Still A, then a shorter piece of the cut record, then zeros: readable by anyone, A untouched.
        assert left == line(A) + line(B)[: torn - stop_after] and owed.read(path)[0] == [A]
        torn -= stop_after
    Scripted(monkeypatch, [1] * 5 + ["all"] * 200)
    journal = Journal(path)  # and when the disk works it is cleared, and the journal goes on
    assert journal.entries == [A] and used(path) == line(A) and journal.torn == torn
    journal.owe([SHORT])
    assert on_disk(path) == [A, SHORT]


def test_an_unfinished_end_too_long_to_be_one_record_is_damage_not_a_crash_s_leftover(tmp_path):
    path = tmp_path / "characters.db.owed"
    Journal(path).owe([A])
    with builtins.open(path, "r+b") as handle:
        handle.seek(len(line(A)))
        handle.write(b"x" * (owed.MAX_LINE + 1))
    before = path.read_bytes()
    with pytest.raises(owed.JournalDamaged, match="too long to be one cut short"):
        Journal(path)
    assert path.read_bytes() == before


def test_a_journal_that_works_again_much_later_holds_only_what_is_still_owed(files, tmp_path, monkeypatch):
    """The journal write fails and keeps failing; the store records the completion meanwhile. When the journal next
    takes a write (a later completion is owed) its unfinished record is finished first and, being recorded already,
    settled at once: a restart replays only what is really owed, and each completion counts once."""
    store, d, (ada,), (a,) = _owing_world(files, tmp_path, monkeypatch, "Ada")
    path = store.path
    try:
        script = Scripted(monkeypatch, [50] + [OSError(5, "Input/output error")] * 400)
        kill(d, a, GUARDIAN_AT, 2)
        first = d.w.progress.owed[0]
        store.fault = None
        d.step()  # the store records it; the journal still cannot be written
        assert store.load(ada["id"]).completed == 1 and d.w.progress.owed == [] and d.w.progress.accepting
        assert d.w.progress.journal.unfinished is not None and on_disk(owed.journal_path(path)) == []
        for _ in range(2):  # out to the hub (the expedition ends) and into a new one
            d.place(a, 128.0, 256.0)
            d.walk_in(-1, a)
        to_layer_2(d, a)
        store.fault = failing
        script.writes.clear()  # the journal works again
        kill(d, a, GUARDIAN_AT, 2)
        second = d.w.progress.owed[0]
        assert second != first and d.w.progress.journal.entries == [second] == on_disk(owed.journal_path(path))
        assert d.w.progress.journal.unfinished is None
    finally:
        store.close()
    monkeypatch.undo()
    store = CharacterStore(path)
    try:
        world = pworld(files, store)
        assert world.progress.recovered == 1 and store.load(ada["id"]).completed == 2  # each counted once
        assert store.load(ada["id"]).unlocks == (UNLOCK,) and on_disk(owed.journal_path(path)) == []
    finally:
        store.close()
