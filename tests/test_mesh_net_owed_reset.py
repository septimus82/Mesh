"""Starting the journal of owed completions over never leaves it believing one thing and holding another (#510,
second review).

When nothing is owed the journal puts a fresh file in place of itself. That takes four steps: make the fresh file,
flush it, move it into place, flush the folder. Any of them can fail. The journal used to keep its old position
whenever one did, including after the move had already happened: the next completion was then written at the old
position of a fresh, empty file, the player was told it was kept, and the next server refused the journal.

Faults are injected (``tests.net_owed_server.ResetFaults``), no disk is made to fail. The folder flush is a POSIX
step: Windows cannot open a folder to flush it and the journal does not try there. It is **simulated** here so that
its failure can be driven on any machine, and failed for real where it exists (the last test). The steps before the
move are reachable on every platform; a refused move is what Windows answers while another program holds the file.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import stat
from pathlib import Path
from typing import Any

import pytest

from mesh_net import owed
from mesh_net.characters import CharacterStore
from mesh_net.owed import RESERVED, Journal, JournalError, Owed
from mesh_net.world import expedition_files
from tests.net_owed_server import Client, ResetFaults, ServerProcess
from tests.test_mesh_net_characters import UNLOCK, P, creds, pworld, to_layer_2
from tests.test_mesh_net_world import R2, kill

pytestmark = pytest.mark.integration
GUARDIAN_AT = (480.0, 256.0)
A = Owed("a" * 32, "ab12", "room:1/guardian/k", UNLOCK)
B = Owed("b" * 32, "ab12", "room:1/guardian/k", UNLOCK)
C = Owed("c" * 32, "ab12", "room:2/guardian/k", UNLOCK)
BEFORE_THE_MOVE = ["temp_create", "temp_flush", "replace"]  # reachable on every platform


def line(*entries: Owed, op: str = "owed") -> bytes:
    return b"".join(owed._line(op, e) for e in entries)


def on_disk(path: Path) -> list[Owed]:
    return owed.read(path)[0]


def used(path: Path) -> bytes:
    return path.read_bytes().rstrip(b"\0")


def injected(monkeypatch: pytest.MonkeyPatch, fail: str | None, simulate_folder: bool = True) -> ResetFaults:
    return ResetFaults(fail, simulate_folder).install(lambda module, name, value: monkeypatch.setattr(
        module, name, value, raising=False))


@pytest.fixture
def journal(tmp_path: Path) -> Journal:
    """A journal holding one owed completion (A)."""
    made = Journal(tmp_path / "characters.db.owed")
    made.owe([A])
    return made


# --- the journal ----------------------------------------------------------------------------------------


def test_started_over_the_journal_is_empty_and_the_next_record_is_its_first(journal, monkeypatch):
    faults = injected(monkeypatch, None)
    journal.settle([A])
    assert faults.log == ["moved into place", "folder flushed"]
    assert journal.end == 0 and journal.entries == [] and not journal.unconfirmed and journal.unusable is None
    assert used(journal.path) == b"" and journal.path.stat().st_size == RESERVED
    journal.owe([B])
    assert journal.path.read_bytes().startswith(line(B)) and used(journal.path) == line(B)
    assert on_disk(journal.path) == [B] == Journal(journal.path).entries  # (a restart recovers it)


@pytest.mark.parametrize("fail", BEFORE_THE_MOVE)
def test_a_start_over_that_fails_before_the_move_leaves_the_old_journal_whole_and_in_use(journal, monkeypatch, fail):
    old = line(A) + line(A, op="done")
    faults = injected(monkeypatch, fail)
    journal.settle([A])
    assert "moved into place" not in faults.log and len(faults.log) == 1  # it stopped at the failing step
    # The old file is the journal still, byte for byte, and the journal knows where its records end.
    assert used(journal.path) == old and journal.end == len(old) and journal.entries == []
    assert not journal.unconfirmed and journal.unusable is None
    journal.owe([B])  # the next completion goes after them (the fault is still there: nothing depends on its going)
    assert used(journal.path) == old + line(B) and on_disk(journal.path) == [B] == Journal(journal.path).entries
    faults.fail = None
    journal.settle([B])  # and when starting over works, it works
    assert journal.end == 0 and used(journal.path) == b"" and "moved into place" in faults.log


def test_moved_into_place_but_the_folder_not_flushed_the_journal_writes_at_the_start_and_calls_nothing_kept(
        journal, monkeypatch):
    faults = injected(monkeypatch, "folder_flush")
    journal.settle([A])
    assert faults.log == ["moved into place", "folder flush fails"]
    # The fresh file is the journal now: its position is read back from it, not kept from the old one.
    assert journal.end == 0 and used(journal.path) == b"" and journal.unconfirmed and journal.unusable is None
    with pytest.raises(JournalError, match="folder cannot be flushed"):
        journal.owe([B])
    # Written at the beginning, whole and flushed (a restart finds it), but not confirmed: the caller is told so.
    assert journal.path.read_bytes().startswith(line(B)) and on_disk(journal.path) == [B] == journal.entries
    with pytest.raises(JournalError, match="folder cannot be flushed"):
        journal.owe([B])  # asked again while the folder still cannot be flushed: the same answer, nothing written twice
    assert used(journal.path) == line(B)
    faults.fail = None
    journal.owe([B])  # the folder flushes: now it can be called kept
    assert not journal.unconfirmed and used(journal.path) == line(B) and faults.log[-1] == "folder flushed"
    journal.owe([C])
    assert on_disk(journal.path) == [B, C] == Journal(journal.path).entries


def test_a_fresh_journal_that_cannot_be_read_back_takes_no_more_writes_and_is_left_as_found(journal, monkeypatch):
    faults = injected(monkeypatch, "scribble")
    journal.settle([A])
    assert faults.log[:2] == ["moved into place", "something else wrote into it"]
    assert journal.unusable is not None and "started over" in journal.unusable
    before = journal.path.read_bytes()
    for _ in range(2):
        with pytest.raises(JournalError, match="nothing more is written to it"):
            journal.owe([B])
    assert journal.path.read_bytes() == before and journal.entries == []  # preserved for whoever looks at it
    with pytest.raises(owed.JournalDamaged):
        Journal(journal.path)  # (and a new server refuses it, as it refuses any damaged journal)


def test_a_fresh_journal_found_holding_a_record_is_not_written_to_either(journal, monkeypatch):
    faults = injected(monkeypatch, "foreign_record")
    faults.foreign = line(C)  # a whole, valid record that this server never wrote
    journal.settle([A])
    assert journal.unusable is not None and "holds records it should not" in journal.unusable
    before = journal.path.read_bytes()
    with pytest.raises(JournalError, match="holds records it should not"):
        journal.owe([B])
    assert journal.path.read_bytes() == before and on_disk(journal.path) == [C]  # not erased, not written after


def test_the_journal_never_starts_over_while_anything_is_owed(journal, monkeypatch):
    journal.owe([B])
    faults = injected(monkeypatch, "temp_create")  # (any attempt to start over would show in the log)
    journal.settle([A])
    assert faults.log == [] and on_disk(journal.path) == [B] == journal.entries
    assert used(journal.path) == line(A, B) + line(A, op="done")


def test_a_second_start_over_that_works_confirms_the_first(journal, monkeypatch):
    faults = injected(monkeypatch, "folder_flush")
    journal.settle([A])
    with pytest.raises(JournalError):
        journal.owe([B])
    assert journal.unconfirmed and on_disk(journal.path) == [B]
    faults.fail = None
    journal.settle([B])  # everything recorded: started over again, and this time the folder flushes
    assert not journal.unconfirmed and journal.end == 0 and used(journal.path) == b""
    journal.owe([C])
    assert on_disk(journal.path) == [C]


# --- through the world: what the player is told, and what a restart finds ------------------------------------


@pytest.fixture(scope="module")
def files():
    return expedition_files()


def failing(point: str) -> None:
    if point == "before_commit":
        raise sqlite3.OperationalError("disk I/O error")


class Played:
    """A character that earns the unlock, the store failing, as often as asked: a world in process."""

    def __init__(self, files: Any, tmp_path: Path) -> None:
        self.path = tmp_path / "characters.db"
        self.store = CharacterStore(self.path, create=True)
        (self.ada,) = creds(self.store, "Ada")
        self.files = files
        self.d = P(pworld(files, self.store))
        self.a = self.d.enter(self.ada)
        self.d.ask(self.a, "create")
        self.journal = owed.journal_path(self.path)

    def earn_owed(self) -> list[str]:
        """Into Layer 2 (out to the hub first, if an expedition is under way) and the guardian down while the store
        fails: what the player was told."""
        d, a = self.d, self.a
        if d.room(a).key == R2:
            for _ in range(2):
                d.place(a, 128.0, 256.0)
                d.walk_in(-1, a)
        d.notices(a)
        to_layer_2(d, a)
        self.store.fault = failing
        kill(d, a, GUARDIAN_AT, 2)
        return d.notices(a)

    def store_works(self) -> list[str]:
        self.store.fault = None
        self.d.step()
        return self.d.notices(self.a)

    def restart(self) -> tuple[int, int, tuple[str, ...]]:
        """Close everything and start a server on the same files: (recovered at start, completed, unlocks)."""
        self.store.close()
        self.store = CharacterStore(self.path)
        world = pworld(self.files, self.store)
        state = self.store.load(self.ada["id"])
        return world.progress.recovered, state.completed, state.unlocks


@pytest.fixture
def played(files, tmp_path):
    game = Played(files, tmp_path)
    yield game
    game.store.close()


def test_after_a_start_over_whose_folder_flush_failed_the_next_unlock_is_not_called_kept_and_is_not_lost(
        played, monkeypatch):
    """The second review's sequence, end to end."""
    assert played.earn_owed() == ["unlock_owed"]
    faults = injected(monkeypatch, "folder_flush")
    assert played.store_works() == ["unlocked"]  # recorded; the journal starts over; the folder flush fails
    assert faults.log == ["moved into place", "folder flush fails"]
    journal = played.d.w.progress.journal
    assert journal.end == 0 and journal.unconfirmed and used(played.journal) == b""

    told = played.earn_owed()  # a second completion, the store failing again, the folder still not flushed
    # Not called kept (it is not known to survive a power cut), never at the old journal's position, and not lost:
    assert told == ["unlock_not_kept"]
    assert played.journal.read_bytes()[:1] != b"\0" and len(on_disk(played.journal)) == 1  # a readable record at byte 0
    assert not played.d.w.progress.accepting

    faults.fail = None
    played.d.step()  # the folder flushes: now it is kept, and said to be
    assert played.d.notices(played.a) == ["unlock_owed"] and not journal.unconfirmed

    monkeypatch.undo()
    assert played.restart() == (1, 2, (UNLOCK,))  # the second completion recorded by the next server, once
    assert played.restart() == (0, 2, (UNLOCK,)) and on_disk(played.journal) == []


def test_a_server_stopped_while_the_folder_still_cannot_be_flushed_loses_nothing_on_restart(played, monkeypatch):
    played.earn_owed()
    injected(monkeypatch, "folder_flush")
    played.store_works()
    assert played.earn_owed() == ["unlock_not_kept"]  # (the folder never flushes in this server's life)
    monkeypatch.undo()
    # The journal is sound and holds the completion: the next server records it. Exactly once, then nothing.
    assert played.restart() == (1, 2, (UNLOCK,))
    assert played.restart() == (0, 2, (UNLOCK,))


@pytest.mark.parametrize("fail", BEFORE_THE_MOVE)
def test_after_a_start_over_that_failed_before_the_move_the_next_unlock_is_kept_and_recovered(played, monkeypatch, fail):
    assert played.earn_owed() == ["unlock_owed"]
    faults = injected(monkeypatch, fail)
    assert played.store_works() == ["unlocked"]
    assert "moved into place" not in faults.log and faults.log
    old = used(played.journal)
    assert old.count(b"\n") == 2 and on_disk(played.journal) == []  # the old journal: owed, then settled; still there

    assert played.earn_owed() == ["unlock_owed"]  # truthfully kept: written after the old journal's records
    assert used(played.journal).startswith(old) and len(on_disk(played.journal)) == 1
    monkeypatch.undo()
    assert played.restart() == (1, 2, (UNLOCK,))  # the first counted once (not replayed), the second once
    assert played.restart() == (0, 2, (UNLOCK,)) and used(played.journal) == b""


def test_a_fresh_journal_that_cannot_be_read_back_means_not_kept_and_no_new_expedition(played, monkeypatch):
    played.earn_owed()
    injected(monkeypatch, "scribble")
    played.store_works()
    before = played.journal.read_bytes()
    assert played.earn_owed() == ["unlock_not_kept"]
    assert played.journal.read_bytes() == before and not played.d.w.progress.accepting  # untouched; fail closed
    assert len(played.d.w.progress.unkept) == 1


# --- a real server process -----------------------------------------------------------------------------------


def test_a_server_killed_after_such_a_start_over_restarts_and_records_what_was_owed(tmp_path):
    """A real server: an unlock owed and then recorded, the journal started over with the folder flush failing
    (simulated in that process), a second unlock owed, and the process killed. The player had been told it was not
    kept; the next server starts on a sound journal and records it, once."""
    path = tmp_path / "characters.db"
    store = CharacterStore(path, create=True)
    try:
        (ada,) = creds(store, "Ada")
    finally:
        store.close()
    cid = ada["id"]

    async def play() -> list[str]:
        server = ServerProcess(path)
        try:
            client = await Client.join(server.port, ada)
            await client.until(lambda c: c.room and c.sheet is not None)
            ask = lambda **command: asyncio.to_thread(server.ask, **command)  # noqa: E731
            await ask(op="to_guardian", characters=[cid])
            await ask(op="fault", store="fail")
            assert (await ask(op="kill_guardian", character=cid))["owed"] == 1
            await client.until(lambda c: "unlock_owed" in c.notices)
            await ask(op="fault", store=None, journal="folder")  # the store works; the folder flush will fail
            assert (await ask(op="step", ticks=1))["owed"] == 0
            await client.until(lambda c: "unlocked" in c.notices)
            await ask(op="leave", characters=[cid])
            assert (await ask(op="to_guardian", characters=[cid]))["rooms"] == [R2]
            await ask(op="fault", store="fail", journal="folder")
            state = await ask(op="kill_guardian", character=cid)
            assert state["owed"] == 1 and state["unkept"] == 1
            await client.until(lambda c: "unlock_not_kept" in c.notices)
            notices = list(client.notices)
            await client.close()
            return notices
        finally:
            server.kill()

    notices = asyncio.run(play())
    assert notices.count("unlock_owed") == 1, "only the first was ever called kept"
    journal = owed.journal_path(path)
    assert journal.read_bytes()[:1] != b"\0" and len(on_disk(journal)) == 1  # sound, the record at its start

    for start in range(2):
        server = ServerProcess(path)
        try:
            state = server.ask(op="state")
            assert state["recovered"] == (1 if start == 0 else 0) and state["owed"] == 0 and state["accepting"]
        finally:
            server.kill()
        check = CharacterStore(path)
        try:
            assert check.load(cid).completed == 2 and check.load(cid).unlocks == (UNLOCK,)
        finally:
            check.close()


# --- the folder flush itself, where the platform has one -------------------------------------------------------


@pytest.mark.skipif(os.name == "nt", reason="Windows cannot open a folder to flush it and the journal does not try there; "
                                            "the default lane runs this on Linux")
def test_the_real_folder_flush_failing_after_the_move(journal, monkeypatch):
    real = os.fsync

    class Os:
        def __getattr__(self, name: str) -> Any:
            return getattr(os, name)

        def fsync(self, fd: int) -> None:
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError(5, "Input/output error")
            real(fd)

    monkeypatch.setattr(owed, "os", Os())
    journal.settle([A])
    assert journal.end == 0 and journal.unconfirmed and used(journal.path) == b""
    with pytest.raises(JournalError, match="folder cannot be flushed"):
        journal.owe([B])
    assert journal.path.read_bytes().startswith(line(B)) and on_disk(journal.path) == [B]
    monkeypatch.undo()
    journal.owe([B])
    assert not journal.unconfirmed and on_disk(journal.path) == [B] == Journal(journal.path).entries
