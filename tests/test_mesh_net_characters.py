"""N8: persistent multiplayer characters (mesh_net.characters, mesh_net.persistence) inside N7's world."""

import asyncio
import hashlib
import json
import os
import sqlite3
import stat
import subprocess
import sys
import time

import pytest

from mesh_net import protocol as wire
from mesh_net.characters import (
    MAX_SLOTS,
    AccessDenied,
    CharacterStore,
    DuplicateClaim,
    InventoryFull,
    NameTaken,
    StoreError,
    StoreUnavailable,
)
from mesh_net.persistence import Refused, check_character, expedition_rules
from mesh_net.scene_room import Unsupported, disposable_project
from mesh_net.server import WorldServer
from mesh_net.world import World, check_frame, check_welcome, expedition_files
from tests.test_mesh_net_world import BANDIT, GUARDIAN, HUB, R1, R2, Driver, Peer, kill, make_world, open_gate

pytestmark = pytest.mark.integration
LIMITS = {"relic_shard": 20, "guardian_sigil": 1}
UNLOCK = "ruins_layer_2_completed"


@pytest.fixture(scope="module")
def files():
    return expedition_files()


@pytest.fixture
def store(tmp_path):
    s = CharacterStore(tmp_path / "characters.db", create=True)
    yield s
    s.close()


def pworld(files, store):
    with disposable_project(files, scaffold=False) as root:
        return World(root, store=store, rules=expedition_rules())


class P(Driver):
    """Driver whose players are characters."""

    def enter(self, credential):
        pid, token = self.w.connect(None, credential)
        self.inbox.setdefault(pid, []).extend(self.w.take(pid))
        return pid

    def sheet(self, pid):
        return self.w.progress.characters[pid]

    def take_loot(self, pid, at):
        self.place(pid, *at)
        self.send(pid, action="take")
        self.step()


def creds(store, *names):
    return [dict(zip(("id", "key"), store.create(name))) for name in names]


def to_layer_2(d, *pids):
    """Hub -> Layer 1 (gate opened by the first) -> Layer 2."""
    d.through_hub_door(*pids)
    open_gate(d, pids[0])
    for pid in pids:
        d.place(pid, 640.0, 256.0)
    d.walk_in(1, *pids)
    assert all(d.room(p).key == R2 for p in pids)


# --- N8B: identity and access -----------------------------------------------------------------------


def test_names_ids_and_keys(store):
    ada, = creds(store, "Ada")
    for bad in ("", " Ada", "Ada ", "a" * 25, "a/b", "Ada\n", "Åsa"):
        with pytest.raises(ValueError):
            store.create(bad)
    with pytest.raises(NameTaken):
        store.create("ADA")  # names are unique regardless of case
    ids = {ada["id"], *(c["id"] for c in creds(store, "Bo", "Cy"))}
    assert len(ids) == 3 and all(len(i) == 32 for i in ids) and len(ada["key"]) == 64
    stored = store.conn.execute("SELECT key_hash FROM characters WHERE id = ?", (ada["id"],)).fetchone()[0]
    assert stored == hashlib.sha256(bytes.fromhex(ada["key"])).digest()  # only the key's hash is kept
    assert ada["key"].encode() not in store.path.read_bytes()


def test_only_the_key_proves_ownership(store):
    ada, bo = creds(store, "Ada", "Bo")
    assert store.authenticate(ada["id"], ada["key"]).name == "Ada"
    for cid, key in ((ada["id"], bo["key"]), (bo["id"], ada["key"]), ("0" * 32, ada["key"]), (ada["id"], "0" * 64),
                     (ada["id"], ada["key"].upper()), (ada["id"], None), ("Ada", ada["key"]), (ada["id"], ada["key"][:-1])):
        with pytest.raises(AccessDenied):  # (unknown and wrong answer alike)
            store.authenticate(cid, key)


def test_one_session_per_character(files, store):
    ada, = creds(store, "Ada")
    d = P(pworld(files, store))
    a = d.enter(ada)
    with pytest.raises(Refused) as refused:
        d.enter(ada)
    assert refused.value.code == "character_in_use" and d.m(a).online
    d.walk(a, 1, 0, 4)
    spot = d.at(a)
    d.w.disconnect(a)
    assert d.enter(ada) == a and d.at(a) == spot  # retained: resumed where it stood
    d.w.disconnect(a)
    d.step(30 * wire.HZ + 1)
    b = d.enter(ada)
    assert b != a and d.sheet(b).id == ada["id"] and d.room(b) is d.w.hub  # expired: a fresh start, same character


def test_selection_switching_and_refusals(files, store):
    ada, bo = creds(store, "Ada", "Bo")
    d = P(pworld(files, store))
    for bad, code in ((None, "character_required"), ({"id": ada["id"]}, "character_required"),
                      ({"id": ada["id"], "key": bo["key"]}, "access_denied")):
        with pytest.raises(Refused) as refused:
            d.w.connect(None, bad)
        assert refused.value.code == code
    a = d.enter(ada)
    token = d.m(a).token
    d.w.disconnect(a)  # (the connection dropped right after choosing: selection is just as resumable)
    b = d.enter(bo)  # another character from the same machine
    assert d.sheet(b).name == "Bo" and d.enter(ada) == a
    with pytest.raises(wire.Invalid):
        d.w.connect(token)  # that resume credential was spent by the character resume
    n7 = Driver(make_world(files))
    with pytest.raises(Refused) as refused:
        n7.w.connect(None, ada)  # a world without a store takes no characters
    assert refused.value.code == "unexpected_character"


# --- N8D: personal loot -----------------------------------------------------------------------------


def test_loot_is_personal_atomic_and_granted_once(files, store):
    ada, bo, cy = creds(store, "Ada", "Bo", "Cy")
    d = P(pworld(files, store))
    a, b, c = d.enter(ada), d.enter(bo), d.enter(cy)
    d.party(a, b)
    d.through_hub_door(a, b)
    kill(d, a, (608.0, 352.0), 3)
    loot = d.w.progress.loot[d.m(a).instance]
    assert set(loot) == {(BANDIT, ada["id"]), (BANDIT, bo["id"])}  # c was in the hub: no share
    for pid in (a, b):  # both at once, then a again: each gets its own, once
        d.place(pid, 568.0, 352.0)
        d.send(pid, action="take")
    d.step()
    d.send(a, action="take")
    d.step()
    assert d.sheet(a).items == (("relic_shard", 1),) and d.sheet(b).items == (("relic_shard", 1),)
    assert d.sheet(c).items == () and not d.w.progress.loot[d.m(a).instance]
    assert store.load(ada["id"]).items == (("relic_shard", 1),)  # (the store, not the cache)
    assert "picked_up" in d.notices(a) and d.notices(c) == []


def test_claims_need_reach(files, store):
    ada, = creds(store, "Ada")
    d = P(pworld(files, store))
    a = d.enter(ada)
    d.ask(a, "create")
    d.through_hub_door(a)
    kill(d, a, (608.0, 352.0), 3)
    d.take_loot(a, (300.0, 352.0))  # out of reach
    assert d.sheet(a).items == () and d.w.progress.loot[d.m(a).instance]


def test_disconnecting_with_a_pickup_queued_and_stale_takes(files, store):
    ada, = creds(store, "Ada")
    d = P(pworld(files, store))
    a = d.enter(ada)
    d.ask(a, "create")
    d.through_hub_door(a)
    kill(d, a, (608.0, 352.0), 3)
    room, eid = d.m(a).instance, d.m(a).eid
    d.place(a, 568.0, 352.0)
    d.send(a, action="take")
    d.w.disconnect(a)  # gone before the tick that would have claimed it
    d.step()
    assert store.load(ada["id"]).items == () and (BANDIT, ada["id"]) in d.w.progress.loot[room]
    assert d.enter(ada) == a and d.m(a).instance == room  # back within the retention window, in the same room
    d.place(a, 568.0, 352.0)
    d.send(a, action="take", room="start:1", entity=eid)  # a stale frame for another room: dropped
    d.step()
    assert store.load(ada["id"]).items == ()
    d.send(a, action="take")
    d.step()
    assert store.load(ada["id"]).items == (("relic_shard", 1),)


def test_a_full_inventory_keeps_the_drop(files, store):
    ada, = creds(store, "Ada")
    d = P(pworld(files, store))
    store.claim(ada["id"], d.w.progress.run, "seed", [("relic_shard", 20)])  # a full stack
    a = d.enter(ada)
    d.ask(a, "create")
    d.through_hub_door(a)
    kill(d, a, (608.0, 352.0), 3)
    d.take_loot(a, (568.0, 352.0))
    assert d.notices(a)[-1] == "inventory_full" and store.load(ada["id"]).items == (("relic_shard", 20),)
    assert (BANDIT, ada["id"]) in d.w.progress.loot[d.m(a).instance]  # still there to take


def test_store_bounds_items_and_quantities(store):
    ada, = creds(store, "Ada")
    store.stack_limits = {**LIMITS, **{f"item_{i}": 5 for i in range(MAX_SLOTS + 1)}}
    for grants in ([("missing", 1)], [("relic_shard", 0)], [("relic_shard", -1)], [("relic_shard", 1000)],
                   [("relic_shard", True)], [("relic_shard", 1.0)], [], [("relic_shard", 1)] * 9):
        with pytest.raises(ValueError):
            store.claim(ada["id"], "run", "x", grants)
    with pytest.raises(InventoryFull):
        store.claim(ada["id"], "run", "y", [("guardian_sigil", 2)])  # not stackable
    for i in range(MAX_SLOTS):
        store.claim(ada["id"], "run", f"slot{i}", [(f"item_{i}", 1)])
    with pytest.raises(InventoryFull):
        store.claim(ada["id"], "run", "one too many", [(f"item_{MAX_SLOTS}", 1)])
    store.claim(ada["id"], "run", "repeat", [("item_0", 1)])
    with pytest.raises(DuplicateClaim):
        store.claim(ada["id"], "run", "repeat", [("item_0", 1)])
    assert dict(store.load(ada["id"]).items)["item_0"] == 2


def test_worlds_refuse_items_their_database_lacks(files, store):
    def edited(path, change):
        doc = json.loads(files[path])
        change(doc)
        return {**files, path: json.dumps(doc).encode()}

    def drops(doc):
        enemy = next(e for e in doc["entities"] if e.get("name") == "Bandit")
        enemy["behaviour_config"]["DropTable"]["drops"] = [{"item_id": "dragon_egg"}]

    with pytest.raises(Unsupported, match="dragon_egg"):
        pworld(edited(f"packs/core_regions/scenes/{R1}.json", drops), store)
    with pytest.raises(Unsupported, match="item database"):
        pworld({k: v for k, v in files.items() if k != "assets/data/items.json"}, store)
    rules = expedition_rules()
    rules["unlocks"]["anything"] = {"label": "x", "room": HUB, "defeat": BANDIT}
    with disposable_project(files, scaffold=False) as root, pytest.raises(Unsupported, match="anything"):
        World(root, store=store, rules=rules)


# --- N8E: unlocks -----------------------------------------------------------------------------------


def test_unlocks_are_earned_once_by_who_was_there(files, store):
    ada, bo, cy = creds(store, "Ada", "Bo", "Cy")
    d = P(pworld(files, store))
    a, b, c = d.enter(ada), d.enter(bo), d.enter(cy)
    d.party(a, b)
    to_layer_2(d, a, b)
    kill(d, a, (480.0, 256.0), 2)
    d.step()  # (a repeated death event is handled once)
    assert UNLOCK in d.sheet(a).unlocks and UNLOCK in d.sheet(b).unlocks and d.sheet(c).unlocks == ()
    assert d.sheet(a).completed == d.sheet(b).completed == 1 and "unlocked" in d.notices(a)
    d.take_loot(a, (440.0, 256.0))
    assert d.sheet(a).items == (("guardian_sigil", 1),)
    # A second expedition: a new instance, the guardian alive again; completion counted, the unlock not again.
    for pid in (a, b):
        d.place(pid, 128.0, 256.0)
    d.walk_in(-1, a, b)  # up to Layer 1
    for pid in (a, b):
        d.place(pid, 128.0, 256.0)
    d.walk_in(-1, a, b)  # to the hub: the expedition ends
    assert not [i for i in d.w.instances if i.startswith(R2)]
    to_layer_2(d, a, b)
    assert d.room(a).room.enemies[GUARDIAN].state.hp == 2
    kill(d, a, (480.0, 256.0), 2)
    assert d.sheet(a).unlocks == (UNLOCK,) and d.sheet(a).completed == 2 and "unlocked" not in d.notices(a)
    with pytest.raises(ValueError):
        store.complete(ada["id"], d.w.progress.run, "made up", "admin")  # no key outside the rules
    with pytest.raises(wire.Invalid):
        d.w.party(a, {"v": 1, "type": "party", "op": "unlock"})  # and no request a client could send


def test_storage_failures_are_never_successes(files, store):
    ada, = creds(store, "Ada")
    d = P(pworld(files, store))
    a = d.enter(ada)
    d.ask(a, "create")

    def broken(point):
        if point == "before_commit":
            raise sqlite3.OperationalError("disk I/O error")

    to_layer_2(d, a)
    store.fault = broken
    kill(d, a, (480.0, 256.0), 2)  # the unlock cannot be written
    d.take_loot(a, (440.0, 256.0))  # nor the sigil
    assert d.sheet(a) == store.load(ada["id"]) and store.load(ada["id"]).unlocks == () and store.load(ada["id"]).items == ()
    # The unlock is owed (kept in the journal, #496: tests/test_mesh_net_owed.py); the sigil was not granted.
    assert d.notices(a) == ["unlock_owed", "storage_failed"] and (GUARDIAN, ada["id"]) in d.w.progress.loot[d.m(a).instance]
    store.fault = None
    d.step()  # the owed completion is retried
    d.take_loot(a, (440.0, 256.0))
    assert store.load(ada["id"]).unlocks == (UNLOCK,) and store.load(ada["id"]).items == (("guardian_sigil", 1),)


# --- N8C: storage guarantees ------------------------------------------------------------------------


def test_an_interrupted_transaction_changes_nothing(store):
    ada, = creds(store, "Ada")
    store.stack_limits, store.unlock_keys = LIMITS, frozenset({UNLOCK})

    def crash(point):
        if point == "before_commit":
            raise sqlite3.OperationalError("simulated failure")

    store.fault = crash
    for action in (lambda: store.claim(ada["id"], "run", "x", [("relic_shard", 2), ("guardian_sigil", 1)]),
                   lambda: store.complete(ada["id"], "run", "c", UNLOCK)):
        with pytest.raises(StoreError):
            action()
    store.fault = None
    assert store.load(ada["id"]).items == () and store.load(ada["id"]).unlocks == () and store.load(ada["id"]).completed == 0
    assert store.conn.execute("SELECT count(*) FROM claims").fetchone()[0] == 0
    assert store.claim(ada["id"], "run", "x", [("relic_shard", 2)]).items == (("relic_shard", 2),)  # nothing stuck


_KILLED = """
import os, sys
from mesh_net.characters import CharacterStore
store = CharacterStore(sys.argv[1])
store.stack_limits = {"relic_shard": 20, "guardian_sigil": 1}
point = sys.argv[3]
store.fault = lambda p: os._exit(9) if p == point else None
store.claim(sys.argv[2], "run", "crash", [("relic_shard", 2), ("guardian_sigil", 1)])
os._exit(0)
"""


@pytest.mark.parametrize("point", ["before_commit", "after_commit"])
def test_a_process_killed_around_its_commit(tmp_path, point):
    """A real process dies (os._exit: no cleanup, no close) just before or just after COMMIT: the store then holds
    all of the claim or none of it, and opens clean."""
    path = tmp_path / "characters.db"
    store = CharacterStore(path, create=True)
    ada, = creds(store, "Ada")
    store.close()
    proc = subprocess.run([sys.executable, "-c", _KILLED, str(path), ada["id"], point], timeout=60,
                          capture_output=True, text=True)
    assert proc.returncode == 9, proc.stderr
    store = CharacterStore(path)
    try:
        state = store.load(ada["id"])
        claims = store.conn.execute("SELECT count(*) FROM claims").fetchone()[0]
        if point == "before_commit":
            assert state.items == () and claims == 0
        else:
            assert state.items == (("guardian_sigil", 1), ("relic_shard", 2)) and claims == 1
    finally:
        store.close()


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def test_unusable_stores_are_refused_and_left_untouched(tmp_path):
    good = tmp_path / "good.db"
    CharacterStore(good, create=True).close()
    garbage = tmp_path / "garbage.db"
    garbage.write_bytes(b"not a database" * 200)
    truncated = tmp_path / "truncated.db"
    truncated.write_bytes(good.read_bytes()[:1500])
    foreign = tmp_path / "foreign.db"
    other = sqlite3.connect(foreign)
    other.execute("CREATE TABLE t (x)")
    other.commit()
    other.close()
    newer = tmp_path / "newer.db"
    newer.write_bytes(good.read_bytes())
    raw = sqlite3.connect(newer)
    raw.execute("UPDATE meta SET value = '2' WHERE key = 'schema_version'")
    raw.commit()
    raw.close()
    cases = [(garbage, "not a usable"), (truncated, "not a usable|damaged|schema"), (foreign, "not a Mesh"),
             (newer, "schema version '2'"), (tmp_path / "missing.db", "no character store")]
    for path, message in cases:
        before = _digest(path)
        with pytest.raises(StoreUnavailable, match=message):
            CharacterStore(path)
        assert _digest(path) == before, path  # never repaired, replaced or created
    with pytest.raises(StoreUnavailable, match="already exists"):
        CharacterStore(good, create=True)
    readonly = tmp_path / "readonly.db"
    readonly.write_bytes(good.read_bytes())
    os.chmod(readonly, stat.S_IREAD)
    try:
        before = _digest(readonly)
        with pytest.raises(StoreUnavailable):
            CharacterStore(readonly)
        assert _digest(readonly) == before
    finally:
        os.chmod(readonly, stat.S_IREAD | stat.S_IWRITE)


def test_one_server_per_store_and_backups(tmp_path):
    path = tmp_path / "characters.db"
    first = CharacterStore(path, create=True)
    ada, = creds(first, "Ada")
    with pytest.raises(StoreUnavailable, match="in use"):
        CharacterStore(path)  # a second server (or a stale one) on the same store
    copy = tmp_path / "backup.db"
    first.backup(copy)
    with pytest.raises(FileExistsError):
        first.backup(copy)
    first.close()
    second = CharacterStore(path)
    restored = CharacterStore(copy)
    try:
        assert restored.authenticate(ada["id"], ada["key"]).name == "Ada" == second.load(ada["id"]).name
    finally:
        restored.close()
        second.close()


def test_the_admin_command_never_prints_a_key(tmp_path):
    store, key_file = tmp_path / "characters.db", tmp_path / "ada.json"
    run = [sys.executable, "-m", "mesh_net.characters"]
    assert subprocess.run([*run, "new-store", str(store)], capture_output=True, timeout=60).returncode == 0
    made = subprocess.run([*run, "create", str(store), "Ada", "--key-file", str(key_file)], capture_output=True,
                          text=True, timeout=60)
    key = json.loads(key_file.read_text(encoding="utf-8"))["key"]
    assert made.returncode == 0 and key not in made.stdout + made.stderr
    again = subprocess.run([*run, "create", str(store), "Bo", "--key-file", str(key_file)], capture_output=True,
                           text=True, timeout=60)
    assert again.returncode == 1 and json.loads(key_file.read_text(encoding="utf-8"))["key"] == key
    listed = subprocess.run([*run, "list", str(store)], capture_output=True, text=True, timeout=60)
    assert "Ada" in listed.stdout and key not in listed.stdout
    assert "Bo" not in listed.stdout  # (refused before anything was made: no character without its key file)


def test_clients_check_character_frames():
    good = {"v": 1, "type": "character", "id": "a" * 32, "name": "Ada", "items": [["relic_shard", 1]],
            "unlocks": [UNLOCK], "completed": 1, "loot": [BANDIT]}
    check_character(good)
    for bad in ({"items": [["relic_shard", 0]]}, {"items": [["Relic", 1]]}, {"unlocks": ["Admin!"]},
                {"completed": -1}, {"id": "A" * 32}, {"name": "x" * 30}, {"loot": [1]}):
        with pytest.raises(wire.Invalid):
            check_character({**good, **bad})


# --- N8F: restart, over sockets -----------------------------------------------------------------------


def test_characters_survive_a_full_server_restart_over_sockets(tmp_path, files):
    """Two characters play (party, Layer 1, Layer 2, the guardian, their sigils, the unlock), disconnect; the
    server and its store close; a new server opens the same store; both come back as themselves, with their items
    and unlock, to fresh rooms."""
    path = tmp_path / "characters.db"
    store = CharacterStore(path, create=True)
    ada, bo = creds(store, "Ada", "Bo")
    d = P(pworld(files, store))
    a, b = d.enter(ada), d.enter(bo)
    d.party(a, b)
    to_layer_2(d, a, b)
    kill(d, a, (480.0, 256.0), 2)
    for pid in (a, b):
        d.take_loot(pid, (440.0, 256.0))
    before = {name: store.load(c["id"]) for name, c in (("Ada", ada), ("Bo", bo))}
    assert all(s.items == (("guardian_sigil", 1),) and s.unlocks == (UNLOCK,) for s in before.values())
    store.close()  # the whole server goes; nothing else is kept

    async def run():
        reopened = CharacterStore(path)
        world = pworld(files, reopened)
        server = WorldServer(world)
        port = await server.start(0)
        peers = []
        try:
            for credential in (ada, bo):
                peer = await SheetPeer.open_as(port, world, credential)
                peers.append(peer)
            for peer in peers:
                await peer.until(lambda p: p.room and p.sheet)
            sheets = {p.sheet["name"]: p.sheet for p in peers}
            for name, state in before.items():
                assert sheets[name]["id"] == state.id and sheets[name]["unlocks"] == [UNLOCK]
                assert sheets[name]["items"] == [["guardian_sigil", 1]]
            assert all(p.room == world.hub.id for p in peers) and not [i for i in world.instances if i.startswith(R2)]
            refused = await SheetPeer.refused_as(port, ada)  # the character is online: a second session is refused
            assert refused == "character_in_use"
            assert reopened.conn.execute("SELECT count(*) FROM claims WHERE run <> ?",
                                         (world.progress.run,)).fetchone()[0] == 0  # the last run's claims are gone
        finally:
            for p in peers:
                await p.close()
            await server.close()
            reopened.close()

    asyncio.run(run())


class SheetPeer(Peer):
    """A socket client (tests.test_mesh_net_world.Peer) that joins as a character and keeps its character frame."""

    @classmethod
    async def open_as(cls, port, world, credential):
        reader, writer = await asyncio.open_connection("127.0.0.1", port, limit=wire.MAX_BYTES)
        writer.write(wire.encode({"v": 1, "type": "join", "resume": None, "character": credential}))
        peer = cls(reader, writer, world)
        hello = await wire.read(reader)
        check_welcome(hello, world.identity)
        peer.player, peer.token, peer.sheet = hello["player"], hello["resume"], None
        return peer

    @staticmethod
    async def refused_as(port, credential):
        reader, writer = await asyncio.open_connection("127.0.0.1", port, limit=wire.MAX_BYTES)
        try:
            writer.write(wire.encode({"v": 1, "type": "join", "resume": None, "character": credential}))
            msg = await wire.read(reader)
            assert msg["type"] == "refused"
            return msg["code"]
        finally:
            writer.close()

    async def until(self, predicate, timeout=10.0):
        async def loop():
            while not predicate(self):
                msg = await wire.read(self.reader)
                check_frame(msg, self.identities)
                if msg["type"] == "enter":
                    self.room, self.key, self.entity, self.state = msg["room"], msg["key"], msg["entity"], msg["state"]
                elif msg["type"] == "room_state" and msg["room"] == self.room:
                    self.state = msg["state"]
                elif msg["type"] == "party":
                    self.party = msg
                elif msg["type"] == "character":
                    self.sheet = msg
        await asyncio.wait_for(loop(), timeout)


# --- N8I: measurements (descriptive, never a gate) ----------------------------------------------------


def test_measure_persistence_costs(tmp_path, files):
    path = tmp_path / "characters.db"
    store = CharacterStore(path, create=True)
    store.stack_limits, store.unlock_keys = LIMITS, frozenset({UNLOCK})
    people = creds(store, *(f"Hero {i}" for i in range(100)))
    loads, claims, completes = [], [], []
    for i, c in enumerate(people):
        t = time.perf_counter()
        store.authenticate(c["id"], c["key"])
        loads.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter()
        store.claim(c["id"], "run", f"c{i}", [("relic_shard", 3), ("guardian_sigil", 1)])
        claims.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter()
        store.complete(c["id"], "run", f"k{i}", UNLOCK)
        completes.append((time.perf_counter() - t) * 1000)
    store.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    size = path.stat().st_size / len(people)
    store.close()
    t = time.perf_counter()
    store = CharacterStore(path)
    world = pworld(files, store)
    restart = (time.perf_counter() - t) * 1000
    d = P(world)
    pids = [d.enter(c) for c in people[:8]]
    ticks = []
    for _ in range(100):
        for pid in pids:
            d.send(pid, 1, 0)
        t = time.perf_counter()
        d.w.step()
        d.w.deliver()
        ticks.append((time.perf_counter() - t) * 1000)
    store.close()
    for series in (loads, claims, completes, ticks):
        series.sort()

    def med(s):
        return f"{s[len(s) // 2]:.2f} ms median, {s[int(len(s) * 0.95)]:.2f} p95"

    print(f"character load {med(loads)}; claim commit {med(claims)}; completion commit {med(completes)}; "
          f"{size / 1024:.1f} KiB per character; restart (store + world) {restart:.0f} ms; "
          f"tick, 8 characters in the hub {med(ticks)}")


def test_every_notice_has_words_in_the_window():
    """The window's caption names each notice the world can send (a missing one raised KeyError in the window)."""
    from mesh_net.world import NOTICES
    from mesh_net.world_client import NOTICE_TEXT

    assert set(NOTICES) <= set(NOTICE_TEXT)


# --- from the fresh independent review: each fails with its fix removed ---------------------------------


def test_two_unlocks_on_one_enemy_are_both_earned(files, store):
    ada, = creds(store, "Ada")
    rules = expedition_rules()
    rules["unlocks"]["guardian_slayer"] = {**rules["unlocks"][UNLOCK], "label": "Guardian slain"}
    with disposable_project(files, scaffold=False) as root:
        d = P(World(root, store=store, rules=rules))
    a = d.enter(ada)
    d.ask(a, "create")
    to_layer_2(d, a)
    kill(d, a, (480.0, 256.0), 2)
    assert d.sheet(a).unlocks == ("guardian_slayer", UNLOCK) and d.sheet(a).completed == 2


def test_drops_a_character_cannot_hold_are_refused_at_load_and_never_stop_the_world(files, store, monkeypatch):
    doc = json.loads(files[f"packs/core_regions/scenes/{R1}.json"])
    enemy = next(e for e in doc["entities"] if e.get("name") == "Bandit")
    enemy["behaviour_config"]["DropTable"]["drops"] = [{"item_id": "relic_shard", "quantity": 1000}]
    with pytest.raises(Unsupported, match="quantities"):
        pworld({**files, f"packs/core_regions/scenes/{R1}.json": json.dumps(doc).encode()}, store)
    ada, = creds(store, "Ada")
    d = P(pworld(files, store))
    a = d.enter(ada)
    d.ask(a, "create")
    d.through_hub_door(a)
    kill(d, a, (608.0, 352.0), 3)

    def refusing(*args, **kwargs):
        raise ValueError("a grant the store refuses")

    monkeypatch.setattr(store, "claim", refusing)
    d.take_loot(a, (568.0, 352.0))  # (raised out of World.step before: the server shut down)
    assert d.notices(a)[-1] == "storage_failed" and (BANDIT, ada["id"]) in d.w.progress.loot[d.m(a).instance]


def test_only_the_entitled_character_can_take_a_drop(files, store):
    ada, bo = creds(store, "Ada", "Bo")
    d = P(pworld(files, store))
    a, b = d.enter(ada), d.enter(bo)
    d.party(a, b)
    d.through_hub_door(a)
    kill(d, a, (608.0, 352.0), 3)  # b arrives after the bandit fell
    d.through_hub_door(b)
    assert d.room(b) is d.room(a)
    d.take_loot(b, (568.0, 352.0))
    assert d.sheet(b).items == () and (BANDIT, ada["id"]) in d.w.progress.loot[d.m(a).instance]


def test_a_completion_is_counted_once_by_the_store(store):
    ada, = creds(store, "Ada")
    store.unlock_keys = frozenset({UNLOCK})
    store.complete(ada["id"], "run", "x", UNLOCK)
    with pytest.raises(DuplicateClaim):
        store.complete(ada["id"], "run", "x", UNLOCK)  # (the world's own guard aside: e.g. a retried completion)
    assert store.load(ada["id"]).completed == 1


def test_a_failed_rollback_fails_every_later_write_visibly(store):
    ada, = creds(store, "Ada")
    store.stack_limits = LIMITS
    real = store.conn

    class NoRollback:
        def __getattr__(self, name):
            return getattr(real, name)

        def execute(self, sql, *args):
            if sql == "ROLLBACK":
                raise sqlite3.OperationalError("cannot roll back")
            return real.execute(sql, *args)

    store.conn = NoRollback()
    store.fault = lambda point: (_ for _ in ()).throw(sqlite3.OperationalError("disk")) if point == "before_commit" else None
    with pytest.raises(StoreError):
        store.claim(ada["id"], "run", "x", [("relic_shard", 1)])
    store.fault = None
    store.conn = real
    with pytest.raises(StoreError, match="restart"):
        store.claim(ada["id"], "run", "y", [("relic_shard", 1)])
    real.execute("ROLLBACK")


def test_the_admin_command_never_leaves_a_character_without_its_key(tmp_path):
    store = tmp_path / "characters.db"
    run = [sys.executable, "-m", "mesh_net.characters"]
    subprocess.run([*run, "new-store", str(store)], check=True, capture_output=True, timeout=60)
    missing = tmp_path / "no such folder" / "ada.json"
    made = subprocess.run([*run, "create", str(store), "Ada", "--key-file", str(missing)], capture_output=True,
                          text=True, timeout=60)
    assert made.returncode == 1 and "Traceback" not in made.stderr
    listed = subprocess.run([*run, "list", str(store)], capture_output=True, text=True, timeout=60)
    assert "Ada" not in listed.stdout  # nothing made: the name is still free
    key_file = tmp_path / "ada.json"
    assert subprocess.run([*run, "create", str(store), "Ada", "--key-file", str(key_file)], capture_output=True,
                          timeout=60).returncode == 0 and json.loads(key_file.read_text(encoding="utf-8"))["key"]


_LEFTOVER = """
import os, sqlite3, sys
c = sqlite3.connect(sys.argv[1], isolation_level=None)
c.execute("PRAGMA journal_mode=WAL")
c.execute("BEGIN IMMEDIATE")
c.execute("UPDATE meta SET value = '2' WHERE key = 'schema_version'")
c.execute("INSERT INTO meta VALUES ('marker', 'kept')")
c.execute("COMMIT")
os._exit(0)  # (a crashed writer: its journal is left behind, never checkpointed)
"""


def test_a_refused_store_keeps_its_content_including_a_leftover_journal(tmp_path):
    path = tmp_path / "characters.db"
    CharacterStore(path, create=True).close()
    subprocess.run([sys.executable, "-c", _LEFTOVER, str(path)], check=True, timeout=60)
    assert (tmp_path / "characters.db-wal").exists()
    with pytest.raises(StoreUnavailable, match="schema version '2'"):
        CharacterStore(path)
    raw = sqlite3.connect(path)
    try:
        assert raw.execute("SELECT value FROM meta WHERE key = 'marker'").fetchone() == ("kept",)  # nothing lost
    finally:
        raw.close()


def test_a_store_with_damaged_pages_is_refused(tmp_path):
    path = tmp_path / "characters.db"
    store = CharacterStore(path, create=True)
    store.stack_limits = {f"item_{i}": 999 for i in range(16)}
    for i in range(40):
        cid, _ = store.create(f"Hero {i}")
        for j in range(16):
            store.claim(cid, "run", f"c{j}", [(f"item_{j}", 1)])
    store.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    store.close()
    data = bytearray(path.read_bytes())
    page = 4096
    last = len(data) // page - 1  # garble a whole data page (the last one), not the header or the schema
    data[last * page:(last + 1) * page] = bytes([0xA5]) * page
    path.write_bytes(bytes(data))
    before = _digest(path)
    with pytest.raises(StoreUnavailable, match="damaged|not a usable"):
        CharacterStore(path)
    assert _digest(path) == before
