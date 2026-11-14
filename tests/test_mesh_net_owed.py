"""Earned multiplayer progression is never lost silently when the character store fails (#496).

A completion the store cannot write is *owed*: written to a journal beside the store (``mesh_net.owed``) before the
player is told, recorded when the store works again, and recorded by the next server if this one stops or is killed
first. Recording is counted once however often it is tried. While anything is owed no new expedition starts.

The first half drives a world in process (the store's fault hook, files reopened independently). The second half
kills real server processes (``tests/net_owed_server.py``) at the points that matter and reopens the store and the
journal from this process. Waits are for answers and frames, never for a time.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from mesh_net import owed
from mesh_net.characters import CharacterStore, DuplicateClaim, StoreError, StoreUnavailable
from mesh_net.characters import main as characters_main
from mesh_net.owed import RESERVED, Journal, JournalDamaged, JournalError, Owed
from mesh_net.persistence import RECORDED_PER_TICK
from mesh_net.world import expedition_files
from tests.net_owed_server import Client, ServerProcess
from tests.test_mesh_net_characters import UNLOCK, P, creds, pworld, to_layer_2
from tests.test_mesh_net_world import GUARDIAN, HUB, R1, R2, kill

pytestmark = pytest.mark.integration
GUARDIAN_AT = (480.0, 256.0)
REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def files():
    return expedition_files()


@pytest.fixture
def stores():
    """Stores opened by a test, closed after it: ``stores(path)`` opens one."""
    opened: list[CharacterStore] = []

    def open_store(path: Path, create: bool = False) -> CharacterStore:
        opened.append(CharacterStore(path, create=create))
        return opened[-1]

    yield open_store
    for store in opened:
        store.close()


def failing(point: str) -> None:
    if point == "before_commit":
        raise sqlite3.OperationalError("disk I/O error")


def no_space(point: str) -> None:
    if point == "before_write":
        raise OSError(28, "No space left on device")


def journal_of(path: Path) -> list[Owed]:
    """What the journal beside a store says, read from the file by this process."""
    return owed.read(owed.journal_path(path))[0]


def sheet_of(path: Path, cid: str):
    """A character as the store file has it, opened afresh (and closed) by this process."""
    store = CharacterStore(path)
    try:
        return store.load(cid)
    finally:
        store.close()


def earn_owed(files, stores, path: Path, *names: str):
    """A world whose characters have just defeated the guardian while the store was failing: (the store, the driver,
    their credentials, their pids). Each has one completion owed."""
    store = stores(path, create=not path.exists())
    people = creds(store, *names)
    d = P(pworld(files, store))
    pids = [d.enter(c) for c in people]
    for other in pids[1:]:
        d.party(pids[0], other)
    if len(pids) == 1:
        d.ask(pids[0], "create")
    to_layer_2(d, *pids)
    store.fault = failing
    kill(d, pids[0], GUARDIAN_AT, 2)
    return store, d, people, pids


# --- in process: kept, recorded, counted once ----------------------------------------------------------


def test_an_owed_unlock_is_kept_before_the_player_is_told_and_recorded_when_the_store_works_again(files, stores, tmp_path):
    path = tmp_path / "characters.db"
    store, d, (ada,), (a,) = earn_owed(files, stores, path, "Ada")
    progress = d.w.progress
    # Not recorded, and not said to be: the player is told it is owed, and it is already on disk.
    assert store.load(ada["id"]).unlocks == () and store.load(ada["id"]).completed == 0 and d.sheet(a).unlocks == ()
    assert d.notices(a) == ["unlock_owed"]
    assert journal_of(path) == [Owed(ada["id"], progress.run, f"{d.m(a).instance}/{GUARDIAN}/{UNLOCK}", UNLOCK)]
    assert progress.owed == journal_of(path) and not progress.unkept and not progress.accepting
    d.step(5)  # the store is still failing: tried again each tick, nothing changes, nothing is said again
    assert d.notices(a) == [] and len(journal_of(path)) == 1 and store.load(ada["id"]).completed == 0
    store.fault = None
    d.step()
    assert store.load(ada["id"]).unlocks == (UNLOCK,) and store.load(ada["id"]).completed == 1
    assert d.sheet(a) == store.load(ada["id"]) and d.notices(a) == ["unlocked"]
    assert journal_of(path) == [] and progress.owed == [] and progress.accepting
    d.step(3)
    assert store.load(ada["id"]).completed == 1  # (and not again)


def test_a_new_server_records_what_an_earlier_one_owed_once_however_often_it_starts(files, stores, tmp_path):
    path = tmp_path / "characters.db"
    store, d, (ada, bo), _ = earn_owed(files, stores, path, "Ada", "Bo")  # two characters, one event
    first_run = d.w.progress.run
    assert len(journal_of(path)) == 2
    store.close()  # the server goes with both owed

    store = stores(path)
    world = pworld(files, store)  # a new run: recovery happens before anyone can join
    assert world.progress.recovered == 2 and world.progress.owed == [] and world.progress.accepting
    for c in (ada, bo):
        assert store.load(c["id"]).unlocks == (UNLOCK,) and store.load(c["id"]).completed == 1
    assert journal_of(path) == []
    # The earlier run's claims were kept for this start (they are what makes the replay countable once) ...
    runs = {r for r, in store.conn.execute("SELECT DISTINCT run FROM claims")}
    assert runs == {first_run}
    store.close()
    for _ in range(2):  # ... and later starts change nothing and forget them
        store = stores(path)
        world = pworld(files, store)
        assert world.progress.recovered == 0
        assert all(store.load(c["id"]).completed == 1 for c in (ada, bo))
        assert store.conn.execute("SELECT count(*) FROM claims").fetchone()[0] == 0
        store.close()


def test_an_earlier_run_s_claims_are_kept_only_while_it_is_owed_something(stores, tmp_path):
    store = stores(tmp_path / "c.db", create=True)
    store.unlock_keys = frozenset({UNLOCK})
    (ada,) = creds(store, "Ada")
    store.begin_run("aa")
    store.complete(ada["id"], "aa", "room:3/guardian/k", UNLOCK)
    store.begin_run("bb", keep={"aa"})
    with pytest.raises(DuplicateClaim):  # still a duplicate: counted once
        store.complete(ada["id"], "aa", "room:3/guardian/k", UNLOCK)
    assert store.load(ada["id"]).completed == 1
    store.begin_run("cc")  # nothing owed any more: forgotten, as before #496
    assert store.conn.execute("SELECT count(*) FROM claims").fetchone()[0] == 0


def test_the_same_unlock_earned_again_in_the_next_run_is_a_completion_of_its_own(files, stores, tmp_path):
    path = tmp_path / "characters.db"
    store, d, (ada,), (a,) = earn_owed(files, stores, path, "Ada")
    owed_completion = d.w.progress.owed[0].completion
    store.close()
    store = stores(path)
    d = P(pworld(files, store))  # recovered here: completed 1
    a = d.enter(ada)
    d.ask(a, "create")
    to_layer_2(d, a)
    kill(d, a, GUARDIAN_AT, 2)
    # Instance ids restart with each server: the same words name a different completion in a different run.
    assert f"{d.m(a).instance}/" in owed_completion
    assert store.load(ada["id"]).completed == 2 and store.load(ada["id"]).unlocks == (UNLOCK,)


def test_a_commit_reported_as_failed_that_happened_is_counted_once(files, stores, tmp_path):
    path = tmp_path / "characters.db"
    store = stores(path, create=True)
    (ada,) = creds(store, "Ada")
    d = P(pworld(files, store))
    a = d.enter(ada)
    d.ask(a, "create")
    to_layer_2(d, a)
    real, calls = store.complete, []

    def committed_but_said_to_fail(*args):
        calls.append(args)
        if len(calls) == 1:
            real(*args)  # the commit happens; the server is told it failed
        raise StoreError("the commit's outcome is unknown" if len(calls) == 1 else "the store is down")

    store.complete = committed_but_said_to_fail
    kill(d, a, GUARDIAN_AT, 2)  # (and the store stays down for the ticks that follow)
    assert store.load(ada["id"]).completed == 1 and len(journal_of(path)) == 1 and "unlock_owed" in d.notices(a)
    store.complete = real
    d.step()  # the store answers "already counted": settled, the sheet read again, the unlock announced once
    assert store.load(ada["id"]).completed == 1 and journal_of(path) == [] and d.w.progress.owed == []
    assert d.sheet(a).unlocks == (UNLOCK,) and d.notices(a) == ["unlocked"]


def test_far_more_than_the_old_queue_held_is_kept_and_recorded_a_few_a_tick(files, stores, tmp_path):
    """The retry queue used to hold 64 and log the rest away. Nothing is dropped now, and recovery is paced."""
    path = tmp_path / "characters.db"
    store, d, (ada, bo), _ = earn_owed(files, stores, path, "Ada", "Bo")
    progress = d.w.progress
    more = [Owed(c["id"], progress.run, f"room:{n}/guardian/{UNLOCK}", UNLOCK) for n in range(200) for c in (ada, bo)]
    progress.owed.extend(more)
    progress._keep(d.w, more)
    assert len(journal_of(path)) == 402 and len(progress.owed) == 402 and not progress.unkept
    assert owed.journal_path(path).stat().st_size > RESERVED  # (past the space kept in advance: it grew)
    store.fault = None
    for tick in range(1, 60):
        d.step()
        assert len(progress.owed) == max(0, 402 - RECORDED_PER_TICK * tick)
        if not progress.owed:
            break
    assert store.load(ada["id"]).completed == store.load(bo["id"]).completed == 201
    assert journal_of(path) == [] and owed.journal_path(path).stat().st_size == RESERVED  # (a fresh file again)


def test_when_the_journal_fails_too_the_player_is_told_it_is_not_saved_and_it_is_kept_as_soon_as_it_can_be(
        files, stores, tmp_path, caplog):
    path = tmp_path / "characters.db"
    store = stores(path, create=True)
    (ada,) = creds(store, "Ada")
    d = P(pworld(files, store))
    a = d.enter(ada)
    d.ask(a, "create")
    to_layer_2(d, a)
    store.fault, d.w.progress.journal.fault = failing, no_space
    with caplog.at_level(logging.ERROR, logger="mesh_net.persistence"):
        kill(d, a, GUARDIAN_AT, 2)
    progress = d.w.progress
    assert d.notices(a) == ["unlock_not_kept"]  # never "unlocked", never "kept"
    assert len(progress.owed) == 1 and progress.unkept == set(progress.owed) and journal_of(path) == []
    assert not progress.accepting
    assert [r for r in caplog.records if "held in memory only" in r.getMessage()], "said in the server's log, once"
    assert len([r for r in caplog.records if "held in memory only" in r.getMessage()]) == 1
    progress.journal.fault = None  # the journal takes writes again, the store still does not
    d.step()
    assert len(journal_of(path)) == 1 and not progress.unkept and d.notices(a) == ["unlock_owed"]
    store.fault = None
    d.step()
    assert store.load(ada["id"]).unlocks == (UNLOCK,) and store.load(ada["id"]).completed == 1
    assert journal_of(path) == [] and d.notices(a) == ["unlocked"] and progress.accepting


def test_no_new_expedition_starts_while_the_store_is_failing_and_nobody_is_trapped(files, stores, tmp_path):
    path = tmp_path / "characters.db"
    store, d, (ada, bo), (a, b) = earn_owed(files, stores, path, "Ada", "Bo")
    (cy,) = creds_while_failing(store, "Cy")
    c = d.enter(cy)
    d.ask(c, "create")
    d.notices(c)
    d.through_hub_door(c)  # a new expedition: refused, with the reason
    assert d.room(c).key == HUB and d.notices(c) == ["storage_unavailable"]
    # The expedition under way goes on: its rooms exist, so its party can still move between them and leave.
    for pid in (a, b):
        d.place(pid, 128.0, 256.0)
    d.walk_in(-1, a, b)
    assert d.room(a).key == d.room(b).key == R1
    for pid in (a, b):
        d.place(pid, 640.0, 256.0)
    d.walk_in(1, a, b)
    assert d.room(a).key == R2  # back down: the same rooms
    for _ in range(2):
        for pid in (a, b):
            d.place(pid, 128.0, 256.0)
        d.walk_in(-1, a, b)
    assert d.room(a).key == d.room(b).key == HUB and not [i for i in d.w.instances if i.startswith(R2)]
    d.notices(a)
    d.through_hub_door(a, b)  # their expedition ended: a new one is refused too
    assert d.room(a).key == HUB and "storage_unavailable" in d.notices(a)
    store.fault = None
    d.step()  # everything owed is recorded: expeditions open again
    assert d.w.progress.accepting
    d.through_hub_door(c)
    assert d.room(c).key == R1


def creds_while_failing(store: CharacterStore, name: str):
    """A character made while the test's fault is set (making one is a commit of its own)."""
    fault, store.fault = store.fault, None
    try:
        return creds(store, name)
    finally:
        store.fault = fault


def test_a_completion_the_store_refuses_for_its_own_reason_stays_in_the_journal_and_blocks_nothing(
        files, stores, tmp_path, caplog):
    path = tmp_path / "characters.db"
    store = stores(path, create=True)
    (ada,) = creds(store, "Ada")
    store.close()
    gone = Owed(ada["id"], "ab12", "room:1/guardian/retired_unlock", "retired_unlock")  # the rules no longer have it
    Journal(owed.journal_path(path)).owe([gone])
    store = stores(path)
    with caplog.at_level(logging.ERROR, logger="mesh_net.persistence"):
        world = pworld(files, store)
    assert world.progress.owed == [gone] and gone in world.progress.refused and world.progress.accepting
    assert journal_of(path) == [gone] and store.load(ada["id"]).completed == 0
    assert any("cannot be recorded" in r.getMessage() for r in caplog.records)
    d = P(world)
    a = d.enter(ada)
    d.ask(a, "create")
    d.through_hub_door(a)
    assert d.room(a).key == R1  # play goes on
    d.step(3)
    assert journal_of(path) == [gone]  # never dropped


# --- the journal file ---------------------------------------------------------------------------------


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


ENTRY = Owed("0" * 32, "ab12", "room:1/guardian/k", UNLOCK)
OTHER = Owed("1" * 32, "ab12", "room:1/guardian/k", UNLOCK)


def test_space_is_kept_in_advance_and_whole_again_when_nothing_is_owed(tmp_path):
    path = tmp_path / "c.db.owed"
    journal = Journal(path)
    assert path.stat().st_size == RESERVED and not path.read_bytes().strip(b"\0") and journal.entries == []
    journal.owe([ENTRY, OTHER, ENTRY])
    assert path.stat().st_size == RESERVED and journal.writes == 1  # one write, inside the space kept
    assert owed.read(path)[0] == [ENTRY, OTHER] == Journal(path).entries
    journal.settle([ENTRY])
    assert owed.read(path)[0] == [OTHER]
    journal.settle([OTHER])
    assert not path.read_bytes().strip(b"\0") and path.stat().st_size == RESERVED and journal.end == 0
    journal.owe([OTHER])  # and it goes on working after starting over
    assert owed.read(path)[0] == [OTHER]


def test_a_last_record_cut_short_by_a_crash_is_cleared_and_nothing_else_is(tmp_path):
    path = tmp_path / "c.db.owed"
    Journal(path).owe([ENTRY])
    whole = owed._line("owed", OTHER)
    end = owed.read(path)[1]
    with open(path, "r+b") as handle:  # a write that stopped half way: no line end
        handle.seek(end)
        handle.write(whole[: len(whole) // 2])
    assert owed.read(path) == ([ENTRY], end, len(whole) // 2)
    journal = Journal(path)
    assert journal.entries == [ENTRY] and journal.torn == len(whole) // 2
    assert owed.read(path) == ([ENTRY], end, 0)  # cleared on disk; the record before it untouched
    journal.owe([OTHER])
    assert owed.read(path)[0] == [ENTRY, OTHER]


def _damaged(path: Path, how: str) -> None:
    Journal(path).owe([ENTRY, OTHER])
    data = bytearray(path.read_bytes())
    end = owed.read(path)[1]
    if how == "a changed byte":
        data[20] ^= 0x01
    elif how == "a record that is not one":
        data[0:9] = b"zzzzzzzz "
    elif how == "data after the end":
        data[end + 10:end + 14] = b"junk"
    elif how == "a settlement of nothing":
        line = owed._line("done", Owed("2" * 32, "ab12", "room:1/guardian/k", UNLOCK))
        data[end:end + len(line)] = line
    elif how == "a field out of range":
        bad = owed._line("owed", Owed("not a character", "ab12", "x", UNLOCK))
        data[end:end + len(bad)] = bad
    path.write_bytes(bytes(data))


DAMAGE = ["a changed byte", "a record that is not one", "data after the end", "a settlement of nothing",
          "a field out of range"]


@pytest.mark.parametrize("how", DAMAGE)
def test_a_damaged_journal_is_refused_and_left_as_it_is(tmp_path, how):
    path = tmp_path / "c.db.owed"
    _damaged(path, how)
    before = _digest(path)
    with pytest.raises(JournalDamaged, match="damaged"):
        Journal(path)
    assert _digest(path) == before


def test_a_world_does_not_start_on_a_damaged_journal_and_changes_nothing(files, stores, tmp_path):
    path = tmp_path / "characters.db"
    store = stores(path, create=True)
    (ada,) = creds(store, "Ada")
    _damaged(owed.journal_path(path), "a changed byte")
    before = _digest(owed.journal_path(path))
    with pytest.raises(StoreUnavailable, match="damaged") as refused:
        pworld(files, store)
    assert isinstance(refused.value, JournalError) and _digest(owed.journal_path(path)) == before
    assert store.load(ada["id"]).completed == 0 and store.conn.execute("SELECT count(*) FROM claims").fetchone()[0] == 0


def test_a_journal_that_cannot_be_written_says_so_and_counts_nothing(tmp_path):
    path = tmp_path / "c.db.owed"
    journal = Journal(path)
    journal.fault = no_space
    with pytest.raises(JournalError, match="cannot be written"):
        journal.owe([ENTRY])
    assert journal.entries == [] and journal.end == 0 and owed.read(path)[0] == []
    journal.fault = None
    journal.owe([ENTRY])
    assert owed.read(path)[0] == [ENTRY]


def test_the_owner_can_list_what_is_owed_without_opening_the_store(files, stores, tmp_path, capsys):
    path = tmp_path / "characters.db"
    store, d, (ada,), _ = earn_owed(files, stores, path, "Ada")
    capsys.readouterr()
    assert characters_main(["owed", str(path)]) == 0  # (the store is open and locked by the "server": not needed)
    out = capsys.readouterr().out
    assert ada["id"] in out and UNLOCK in out and "1 owed" in out and ada["key"] not in out


# --- real processes, killed --------------------------------------------------------------------------


def _new_store(path: Path, *names: str):
    store = CharacterStore(path, create=True)
    try:
        return creds(store, *names)
    finally:
        store.close()


async def _joined(server: ServerProcess, *people) -> list[Client]:
    clients = [await Client.join(server.port, c) for c in people]
    for client in clients:
        await client.until(lambda c: c.room and c.sheet is not None)
    return clients


def test_a_server_killed_with_unlocks_owed_loses_none_of_them(tmp_path):
    """#496: two characters earn the unlock, the store fails, the process is killed with both owed. The next server
    records both, once; killing and starting it again changes nothing."""
    path = tmp_path / "characters.db"
    ada, bo = _new_store(path, "Ada", "Bo")
    ids = [ada["id"], bo["id"]]

    async def play() -> None:
        server = ServerProcess(path)
        try:
            clients = await _joined(server, ada, bo)
            assert (await asyncio.to_thread(server.ask, op="to_guardian", characters=ids))["rooms"] == [R2, R2]
            await asyncio.to_thread(server.ask, op="fault", store="fail")
            assert (await asyncio.to_thread(server.ask, op="kill_guardian", character=ids[0]))["owed"] == 2
            for client in clients:  # each was told, over its socket, that the unlock is owed (not that it is saved)
                await client.until(lambda c: "unlock_owed" in c.notices)
                assert "unlocked" not in client.notices and client.sheet["unlocks"] == []
            for client in clients:
                await client.close()
        finally:
            server.kill()  # no shutdown: the process is gone with both owed

    asyncio.run(play())
    assert [(e.character, e.unlock) for e in journal_of(path)] == [(ids[0], UNLOCK), (ids[1], UNLOCK)]
    assert all(sheet_of(path, c).unlocks == () and sheet_of(path, c).completed == 0 for c in ids)

    server = ServerProcess(path)  # the next server records them before it listens
    try:
        state = server.ask(op="state")
        assert state["recovered"] == 2 and state["owed"] == 0 and state["accepting"]
    finally:
        server.kill()
    assert journal_of(path) == []
    assert all(sheet_of(path, c).unlocks == (UNLOCK,) and sheet_of(path, c).completed == 1 for c in ids)

    async def rejoin() -> None:
        server = ServerProcess(path)  # and a third start, joined: the same, once
        try:
            assert server.ask(op="state")["recovered"] == 0
            client, = await _joined(server, ada)
            assert client.sheet["unlocks"] == [UNLOCK] and client.sheet["completed"] == 1
            await client.close()
        finally:
            server.kill()

    asyncio.run(rejoin())
    assert all(sheet_of(path, c).completed == 1 for c in ids)


def test_a_server_killed_while_recording_what_was_owed_still_counts_each_once(files, stores, tmp_path):
    path = tmp_path / "characters.db"
    store, d, (ada, bo), _ = earn_owed(files, stores, path, "Ada", "Bo")
    store.close()
    ids = [ada["id"], bo["id"]]

    server = ServerProcess(path, "--replay-exit", "1")  # dies after recording the first, before settling it
    try:
        assert server.port == 0 and server.exited() == 9
    finally:
        server.kill()
    done = [sheet_of(path, c).completed for c in ids]
    assert done == [1, 0] and len(journal_of(path)) == 2  # one recorded; the journal still says both are owed

    server = ServerProcess(path)  # the next one: the first is refused as a duplicate, the second recorded
    try:
        assert server.ask(op="state")["recovered"] == 2
    finally:
        server.kill()
    assert [sheet_of(path, c).completed for c in ids] == [1, 1] and journal_of(path) == []
    assert all(sheet_of(path, c).unlocks == (UNLOCK,) for c in ids)


@pytest.mark.parametrize(("store_fault", "journal_fault", "recorded_at_death", "owed_at_death"), [
    ("fail", "exit_after", 0, 1),       # the journal record is durable, the process dies before anyone is told
    ("uncertain", "exit_after", 1, 1),  # the commit happened, the server was told it failed, then died
    ("fail", "exit", 0, 0),             # it dies before the journal record exists: nothing was durable or said
], ids=["after the journal write", "after a commit reported as failed", "before the journal write"])
def test_a_server_dying_at_the_moment_a_completion_becomes_owed(tmp_path, store_fault, journal_fault,
                                                                 recorded_at_death, owed_at_death):
    path = tmp_path / "characters.db"
    ada, = _new_store(path, "Ada")

    async def play() -> int:
        server = ServerProcess(path)
        try:
            client, = await _joined(server, ada)
            await asyncio.to_thread(server.ask, op="to_guardian", characters=[ada["id"]])
            await asyncio.to_thread(server.ask, op="fault", store=store_fault, journal=journal_fault)
            code = await asyncio.to_thread(server.dies, op="kill_guardian", character=ada["id"])
            await client.until(lambda c: c.gone)
            assert "unlocked" not in client.notices and "unlock_owed" not in client.notices  # nothing was claimed
            await client.close()
            return code
        finally:
            server.kill()

    assert asyncio.run(play()) == 9
    assert sheet_of(path, ada["id"]).completed == recorded_at_death and len(journal_of(path)) == owed_at_death

    server = ServerProcess(path)
    try:
        state = server.ask(op="state")
        assert state["recovered"] == owed_at_death and state["owed"] == 0 and state["accepting"]
    finally:
        server.kill()
    after = sheet_of(path, ada["id"])
    # Owed at death: recorded now, exactly once (also when the commit had happened after all). Not owed at death:
    # the process died before the completion was written anywhere or anyone was told; the files are sound.
    assert after.completed == owed_at_death and after.unlocks == ((UNLOCK,) if owed_at_death else ())
    assert journal_of(path) == []


def test_with_store_and_journal_both_failing_the_loss_is_said_never_silent(tmp_path):
    """The limit, stated: with no storage that takes a write, a kill loses the completion. The player was told it was
    not saved, the server's log names it, new expeditions were refused, and the files stay sound."""
    path = tmp_path / "characters.db"
    ada, bo = _new_store(path, "Ada", "Bo")

    async def play() -> str:
        server = ServerProcess(path)
        try:
            a, b = await _joined(server, ada, bo)
            await asyncio.to_thread(server.ask, op="to_guardian", characters=[ada["id"]])
            await asyncio.to_thread(server.ask, op="fault", store="fail", journal="fail")
            state = await asyncio.to_thread(server.ask, op="kill_guardian", character=ada["id"])
            assert state["owed"] == 1 and state["unkept"] == 1 and not state["accepting"]
            await a.until(lambda c: "unlock_not_kept" in c.notices)
            assert "unlocked" not in a.notices and "unlock_owed" not in a.notices
            await asyncio.to_thread(server.ask, op="party_of_one", characters=[bo["id"]])
            assert (await asyncio.to_thread(server.ask, op="enter", characters=[bo["id"]]))["rooms"] == [HUB]
            await b.until(lambda c: "storage_unavailable" in c.notices)
            for client in (a, b):
                await client.close()
        finally:
            server.kill()
        return server.stderr()

    log = asyncio.run(play())
    assert "held in memory only" in log and ada["id"] in log
    assert journal_of(path) == [] and sheet_of(path, ada["id"]).completed == 0  # lost, as it was said it would be
    server = ServerProcess(path)  # and the next server starts on sound files
    try:
        assert server.ask(op="state")["accepting"]
    finally:
        server.kill()


def _run_server(path: Path) -> subprocess.Popen[str]:
    return subprocess.Popen([sys.executable, "-m", "mesh_net.server", "--expedition", "--store", str(path), "--port", "0"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=REPO)


def test_the_shipped_server_records_what_is_owed_when_it_starts(files, stores, tmp_path):
    path = tmp_path / "characters.db"
    store, d, (ada,), _ = earn_owed(files, stores, path, "Ada")
    store.close()
    proc = _run_server(path)
    watchdog = threading.Timer(120, proc.kill)  # (a server that neither listens nor exits ends the test, not hangs it)
    watchdog.start()
    try:
        lines = []
        for line in proc.stdout:  # (until it listens: every line before that is read, none waited for by time)
            lines.append(line.strip())
            if line.startswith("Mesh room listening"):
                break
    finally:
        watchdog.cancel()
        proc.kill()
        proc.communicate(timeout=30)
    assert "Mesh owed completions: 1 recorded from earlier runs, 0 still owed" in lines, lines
    assert sheet_of(path, ada["id"]).unlocks == (UNLOCK,) and sheet_of(path, ada["id"]).completed == 1
    assert journal_of(path) == []


def test_the_shipped_server_refuses_a_damaged_journal_and_changes_nothing(tmp_path):
    path = tmp_path / "characters.db"
    _new_store(path, "Ada")
    _damaged(owed.journal_path(path), "a changed byte")
    before = _digest(owed.journal_path(path))
    proc = _run_server(path)
    out, err = proc.communicate(timeout=120)
    assert proc.returncode == 1 and "damaged" in err and "Traceback" not in err, (out, err)
    assert "Mesh room listening" not in out and _digest(owed.journal_path(path)) == before
