"""N7: many Studio-authored rooms, transitions and parties under one graphics-free authority (mesh_net.world)."""

import asyncio
import json
import subprocess
import sys
import time
from contextlib import AsyncExitStack

import pytest

from mesh_net import protocol as wire
from mesh_net.scene_room import Unsupported, disposable_project
from mesh_net.server import WorldServer
from mesh_net.world import (
    EXPEDITION_FILES, MAX_INSTANCES, MAX_INVITES, MAX_PARTY, RETAIN_TICKS, TransferResult, World, check_frame,
    check_welcome, expedition_files,
)

HUB, R1, R2 = "start", "ancient_ruins_layer_1", "ancient_ruins_layer_2"
LEVER1, GATE1, BANDIT = (f"{R1}_lever_352_352_0_0", f"{R1}_gate_432_256_0_0", f"{R1}_bandit_608_352_0_0")
GUARDIAN = f"{R2}_guardian_480_256_0_0"
SCENES = {HUB: "packs/core_regions/scenes/start.json", R1: f"packs/core_regions/scenes/{R1}.json",
          R2: f"packs/core_regions/scenes/{R2}.json"}


def make_world(files=None) -> World:
    with disposable_project(files or expedition_files(), scaffold=False) as root:
        return World(root)


@pytest.fixture(scope="module")
def files():
    return expedition_files()


@pytest.fixture
def world(files):
    return make_world(files)


class Driver:
    """Plays clients against a World directly: inputs, party requests, ticks and what each player receives."""

    def __init__(self, world):
        self.w, self.seq, self.inbox = world, {}, {}

    def join(self, resume=None):
        pid, token = self.w.connect(resume)
        self.inbox.setdefault(pid, []).extend(self.w.take(pid))
        return pid, token

    def m(self, pid):
        return self.w.members[pid]

    def room(self, pid):
        return self.w.instances[self.m(pid).instance]

    def player(self, pid):
        return self.room(pid).room.players[self.m(pid).eid]

    def at(self, pid):
        b = self.player(pid).body
        return round(b.center_x, 2), round(b.center_y, 2)

    def place(self, pid, x, y, facing=0):
        p = self.player(pid)
        p.body.center_x, p.body.center_y, p.facing = x, y, facing
        self.room(pid).touching[self.m(pid).eid] = self.w._doors_touched(self.room(pid), p.body)

    def send(self, pid, dx=0, dy=0, action=None, room=None, entity=None):
        self.seq[pid] = self.seq.get(pid, 0) + 1
        m = self.m(pid)
        msg = {"v": 1, "type": "input", "room": room or m.instance, "entity": entity or m.eid or 1,
               "seq": self.seq[pid], "dx": dx, "dy": dy}
        if action:
            msg["action"] = action
        self.w.input(pid, msg)

    def ask(self, pid, op, **fields):
        self.w.party(pid, {"v": 1, "type": "party", "op": op, **fields})

    def step(self, n=1):
        for _ in range(n):
            self.w.step()
            for pid, frames in self.w.deliver().items():
                self.inbox.setdefault(pid, []).extend(frames)

    def walk(self, pid, dx, dy, ticks, *others):
        for _ in range(ticks):
            for p in (pid, *others):
                if self.m(p).online:
                    self.send(p, dx, dy)
            self.step()

    def frames(self, pid, kind):
        if pid in self.w.members and self.m(pid).online:
            self.inbox.setdefault(pid, []).extend(self.w.take(pid))  # (requests answer at once, not on a tick)
        found = [f for f in self.inbox.get(pid, []) if f["type"] == kind]
        self.inbox[pid] = [f for f in self.inbox.get(pid, []) if f["type"] != kind]
        return found

    def notices(self, pid):
        """Notices other than "you were invited" (which every invitation sends)."""
        return [f["code"] for f in self.frames(pid, "notice") if f["code"] != "invited"]

    def party(self, a, b):
        """a invites b (a leads); b accepts."""
        self.ask(a, "invite", player=b)
        self.ask(b, "accept", party=self.m(a).party)
        assert self.m(b).party == self.m(a).party

    def walk_in(self, dx, *pids):
        """Each walks (dx) until a door has taken it to another room, or 8 ticks pass; then stands still."""
        start = {pid: self.m(pid).instance for pid in pids}
        for _ in range(8):
            for pid in pids:
                self.send(pid, dx if self.m(pid).instance == start[pid] else 0, 0)
            self.step()

    def through_hub_door(self, *pids):
        """Stand just left of the hub's door and step in."""
        for pid in pids:
            self.place(pid, 640.0, 256.0)
        self.walk_in(1, *pids)

    def to_layer_2(self, *pids):
        """From Layer 1 (its gate open), just left of the door down, step in."""
        for pid in pids:
            self.place(pid, 640.0, 256.0)
        self.walk_in(1, *pids)


def open_gate(d, pid):
    d.place(pid, 352.0, 300.0, facing=1)  # below the lever, facing up
    d.send(pid, action="use")
    d.step()
    assert GATE1 in d.room(pid).room.snapshot()["open"]


def kill(d, pid, enemy_at, hp):
    x, y = enemy_at
    d.place(pid, x - 40.0, y, facing=0)
    for _ in range(hp):
        d.send(pid, action="attack")
        d.step(11)  # Combat's 0.5 s cooldown


# --- the room package ---------------------------------------------------------------------------


@pytest.mark.integration
def test_committed_world_is_a_fresh_studio_build(files):
    sys.path.insert(0, "tooling")
    try:
        from make_expedition import build
    finally:
        sys.path.remove("tooling")
    assert {rel: json.loads(text) for rel, text in build().items()} == {rel: json.loads(files[rel]) for rel in EXPEDITION_FILES}


@pytest.mark.integration
def test_the_rooms_are_ordinary_single_player_scenes(files):
    """Each room loads in single-player through the engine's own loader; nothing in N7 is a new format."""
    code = ("import sys, json; from engine.scene_loader import SceneLoader; from engine.migrations import migrate_payload\n"
            "for p in sys.argv[1:]:\n"
            "    d = SceneLoader().load(p) if hasattr(SceneLoader(), 'load') else None\n"
            "    assert json.load(open(p, encoding='utf-8'))['entities']\n")
    with disposable_project(files, scaffold=False) as root:
        world = json.loads((root / "packs/core_regions/worlds/main.json").read_text(encoding="utf-8"))
        assert {k: v["path"] for k, v in world["scenes"].items()} == SCENES
        assert {k: v["tags"] for k, v in world["scenes"].items()} == {HUB: ["start"], R1: ["expedition"], R2: ["expedition"]}
        from engine.scene_loader import SceneLoader
        from engine.migrations import migrate_payload
        from engine.schema_validation import validate
        for path in SCENES.values():
            doc = migrate_payload("scene", json.loads((root / path).read_text(encoding="utf-8")))
            validate(doc, "scene.schema.json", root / path)
            assert SceneLoader().apply_scene_defaults(doc)["entities"]
    assert code  # (the engine loader itself runs in the GPU test's windows)


@pytest.mark.integration
def test_world_authority_runs_without_graphics():
    code = ("import sys; from mesh_net.world import *; from mesh_net.server import WorldServer\n"
            "from mesh_net.scene_room import disposable_project\n"
            "with disposable_project(expedition_files(), scaffold=False) as root:\n    World(root)\n"
            "bad = [m for m in sys.modules if m.split('.')[0] in ('arcade', 'pyglet') or m in ('engine.game', 'engine.studio')]\n"
            "assert not bad, bad\n"
            "import threading; assert threading.active_count() == 1\n")
    subprocess.run([sys.executable, "-c", code], check=True, timeout=120)


# --- N7B: isolation ------------------------------------------------------------------------------


@pytest.mark.integration
def test_room_scoped_entity_ids_collide_without_crossing(world):
    d = Driver(world)
    a, _ = d.join()
    b, _ = d.join()
    c, _ = d.join()
    d.party(a, b)
    d.through_hub_door(a, b)
    assert d.room(a).key == R1 and d.room(a) is d.room(b) and d.room(c).key == HUB
    assert d.m(a).eid == 1 and d.m(c).eid == 3 and 1 not in d.w.hub.room.players  # eid 1: a new player, in L1 only
    d.ask(c, "create")
    d.through_hub_door(c)
    assert d.m(c).eid == 1 and d.room(c) is not d.room(a)  # eid 1 in two rooms names two players
    before = d.at(a)
    d.walk(c, 1, 0, 5)
    assert d.at(a) == before  # c's input moved c only


@pytest.mark.integration
def test_no_room_state_reaches_another_room(world):
    d = Driver(world)
    a, _ = d.join()
    b, _ = d.join()
    c, _ = d.join()
    d.party(a, b)
    d.through_hub_door(a, b)
    d.step(3)
    for pid in (a, b, c):
        rooms = {f["room"] for f in d.frames(pid, "room_state")} | {f["room"] for f in d.frames(pid, "enter")}
        assert rooms <= {d.m(pid).instance, d.w.hub.id}
    d.inbox = {}
    d.step(2)
    assert [f["room"] for f in d.frames(c, "room_state")] == [d.w.hub.id] * 2
    assert {f["room"] for f in d.frames(a, "room_state")} == {d.m(a).instance}


@pytest.mark.integration
def test_interactions_and_input_cannot_reach_another_room(world):
    d = Driver(world)
    a, _ = d.join()
    b, _ = d.join()
    for pid in (a, b):
        d.ask(pid, "create")
    d.through_hub_door(a)
    d.through_hub_door(b)
    ra, rb = d.room(a), d.room(b)
    assert ra.key == rb.key == R1 and ra is not rb
    open_gate(d, a)
    assert GATE1 not in rb.room.snapshot()["open"] and not rb.room.used
    # b names a's room and a's entity: dropped (it is not b's room), nothing in a's room moves or acts.
    d.place(b, 352.0, 300.0, facing=1)
    before = d.at(a)
    d.send(b, 1, 0, action="use", room=ra.id, entity=d.m(a).eid)
    d.step()
    assert d.at(a) == before and not rb.room.used
    with pytest.raises(wire.Invalid):
        d.send(b, room="not a room")


@pytest.mark.integration
def test_enemies_and_loot_are_each_rooms_own(world):
    d = Driver(world)
    a, _ = d.join()
    b, _ = d.join()
    for pid in (a, b):
        d.ask(pid, "create")
        d.through_hub_door(pid)
    kill(d, a, (608.0, 352.0), 3)
    ra, rb = d.room(a).room, d.room(b).room
    assert ra.enemies[BANDIT].state.dead and ra.snapshot()["drops"] == [BANDIT]
    assert rb.enemies[BANDIT].state.hp == 3 and rb.snapshot()["drops"] == []
    d.place(b, 568.0, 352.0)
    d.send(b, action="take")
    d.step()
    assert ra.snapshot()["drops"] == [BANDIT] and rb.snapshot()["loot"] == []
    d.send(a, action="take")
    d.step()
    assert ra.snapshot()["loot"] == [[BANDIT, d.m(a).eid]]
    # Layer 2's enemy is its own too, and unseeded tables would roll per instance.
    open_gate(d, a)
    d.to_layer_2(a)
    assert d.room(a).key == R2 and d.room(a).room.enemies[GUARDIAN].state.hp == 2


# --- N7C: transitions ----------------------------------------------------------------------------


@pytest.mark.integration
def test_a_door_fires_once_per_walk_in(world):
    d = Driver(world)
    a, _ = d.join()
    d.ask(a, "create")
    d.through_hub_door(a)
    assert d.room(a).key == R1 and d.at(a) == (64.0, 160.0)  # the arrival marker
    enters = d.frames(a, "enter")
    assert [f["key"] for f in enters] == [HUB, R1]
    # Standing in a door (arrived inside its area, or stayed there) never fires it again.
    d.place(a, 64.0, 256.0)  # inside L1's door to the hub, placed there: not walked in
    d.walk(a, 0, 0, 5)
    assert d.room(a).key == R1
    d.walk(a, 0, 1, 1)  # still inside
    assert d.room(a).key == R1
    d.walk(a, 1, 0, 10)
    d.walk_in(-1, a)  # out, then back in
    assert d.room(a).key == HUB and d.at(a) == (704.0, 160.0)
    assert [f["key"] for f in d.frames(a, "enter")] == [HUB]


@pytest.mark.integration
def test_unknown_or_unreachable_destinations_are_refused_at_load(files):
    def edited(path, change):
        doc = json.loads(files[path])
        change(doc)
        return {**files, path: json.dumps(doc).encode()}

    def door(doc):
        return next(e for e in doc["entities"] if e.get("tag") == "door")["behaviour_config"]["SceneTransition"]

    hub = SCENES[HUB]
    cases = [
        (lambda doc: door(doc).update(target_scene="nowhere"), "not a room of this world"),
        (lambda doc: door(doc).update(spawn_id="missing"), "lacks"),
        (lambda doc: [door(doc).pop(k) for k in ("area_width", "area_height")], "picture door"),
        (lambda doc: door(doc).update(trigger_on_touch=False, allow_interact=True), "walked into"),
        (lambda doc: door(doc).update(once=True), "once"),
    ]
    for change, message in cases:
        with pytest.raises(Unsupported, match=message):
            make_world(edited(hub, change))
    world_doc = json.loads(files["packs/core_regions/worlds/main.json"])
    world_doc["scenes"]["start"]["tags"] = ["expedition"]
    with pytest.raises(Unsupported, match="start room"):
        make_world({**files, "packs/core_regions/worlds/main.json": json.dumps(world_doc).encode()})


@pytest.mark.integration
def test_stale_input_from_the_previous_room_is_dropped(world):
    d = Driver(world)
    a, _ = d.join()
    d.ask(a, "create")
    old_room, old_eid = d.w.hub.id, d.m(a).eid
    d.through_hub_door(a)
    at = d.at(a)
    for _ in range(5):  # still naming the hub: in flight when the transfer happened
        d.send(a, -1, 0, action="attack", room=old_room, entity=old_eid)
        d.step()
    assert d.at(a) == at and d.room(a).key == R1 and old_eid not in d.w.hub.room.players


@pytest.mark.integration
def test_failed_destination_preparation_changes_nothing(world):
    d = Driver(world)
    a, _ = d.join()
    d.ask(a, "create")

    def broken(key):
        raise OSError("disk gone")

    d.w.prepare_hook = broken
    instances = set(d.w.instances)
    d.through_hub_door(a)
    assert d.room(a) is d.w.hub and set(d.w.instances) == instances and d.notices(a) == ["transfer_failed"]
    assert d.player(a).body.center_x > 640  # where they stood, in the door: walking out and in again retries
    d.w.prepare_hook = None
    d.walk(a, -1, 0, 8)
    d.walk(a, 1, 0, 8)
    assert d.room(a).key == R1


@pytest.mark.integration
def test_disconnect_right_after_a_transfer_resumes_in_the_destination(world):
    d = Driver(world)
    a, token = d.join()
    d.ask(a, "create")
    d.place(a, 640.0, 256.0)
    d.send(a, 1, 0)
    for _ in range(6):
        d.send(a, 1, 0)
        d.w.step()
        if d.room(a).key == R1:
            break
    room = d.m(a).instance
    d.w.disconnect(a)  # before the enter frame was ever delivered
    assert room in d.w.instances  # kept for the retained player
    pid, _ = d.join(token)
    assert pid == a and d.m(a).instance == room and d.at(a) == (64.0, 160.0)
    assert d.frames(a, "enter")[-1]["room"] == room


@pytest.mark.integration
def test_departed_rooms_are_destroyed(world):
    d = Driver(world)
    a, ta = d.join()
    b, tb = d.join()
    d.party(a, b)
    d.through_hub_door(a, b)
    r1 = d.m(a).instance
    for pid in (a, b):  # back to the hub through Layer 1's door
        d.place(pid, 128.0, 256.0)
    d.walk(a, -1, 0, 6, b)
    assert d.room(a) is d.w.hub and d.room(b) is d.w.hub and r1 not in d.w.instances
    d.through_hub_door(a, b)
    r1b = d.m(a).instance
    assert r1b != r1  # a new instance, never the old id
    d.w.disconnect(a)
    d.w.disconnect(b)
    d.step(RETAIN_TICKS - 1)
    assert r1b in d.w.instances
    d.step(2)
    assert r1b not in d.w.instances and not d.w.parties and not d.w.members and list(d.w.instances) == [d.w.hub.id]


# --- N7D: parties --------------------------------------------------------------------------------


@pytest.mark.integration
def test_forged_and_malformed_party_requests(world):
    d = Driver(world)
    a, _ = d.join()
    b, _ = d.join()
    c, _ = d.join()
    d.party(a, b)
    d.ask(b, "invite", player=c)  # not the leader
    d.ask(a, "invite", player=a)
    d.ask(a, "invite", player=99)
    d.ask(c, "accept", party=d.m(a).party)  # never invited
    assert d.notices(b) == ["not_leader"] and d.notices(a) == ["no_player", "no_player"]
    assert d.notices(c) == ["no_invite"] and d.m(c).party is None
    for bad in ({"op": "invite", "player": b, "party": 1}, {"op": "promote"}, {"op": "accept"},
                {"op": "invite", "player": "2"}, {"op": "leave", "v": 2}):
        with pytest.raises(wire.Invalid):
            d.w.party(c, {"v": 1, "type": "party", **bad})


@pytest.mark.integration
def test_declined_and_simultaneous_invitations(world):
    d = Driver(world)
    a, b, c, e = (d.join()[0] for _ in range(4))
    d.ask(a, "invite", player=b)
    d.ask(b, "invite", player=a)  # at once: a's came first, so a leads and b's is refused
    assert d.m(a).party is not None and d.m(b).party is None and d.notices(b) == ["busy"]
    d.ask(b, "accept", party=d.m(a).party)
    assert d.m(b).party == d.m(a).party
    d.ask(e, "create")
    d.ask(a, "invite", player=c)
    d.ask(e, "invite", player=c)
    assert sorted(p for p, _ in d.w.party_view(d.m(c))["invites"]) == sorted([d.m(a).party, d.m(e).party])
    d.ask(c, "decline", party=d.m(a).party)
    d.ask(c, "accept", party=d.m(a).party)
    assert d.notices(c) == ["no_invite"] and d.m(c).party is None
    d.ask(c, "accept", party=d.m(e).party)
    assert d.m(c).party == d.m(e).party and d.w.party_view(d.m(c))["invites"] == []
    d.ask(c, "create")
    d.ask(a, "invite", player=c)
    assert d.notices(c) == ["in_party"] and d.notices(a) == ["busy"]
    members = [p for party in d.w.parties.values() for p in party.members]
    assert len(members) == len(set(members))  # nobody is in two parties


@pytest.mark.integration
def test_party_size_and_invitation_bounds(world):
    d = Driver(world)
    pids = [d.join()[0] for _ in range(wire.MAX_PLAYERS)]
    leader, *rest = pids
    for pid in rest[:MAX_PARTY - 1]:
        d.party(leader, pid)
    late = rest[MAX_PARTY - 1]
    d.ask(leader, "invite", player=late)
    d.ask(late, "accept", party=d.m(leader).party)
    assert d.notices(late)[-1] == "party_full" and len(d.w.parties[d.m(leader).party].members) == MAX_PARTY
    target = rest[-1]
    d.ask(target, "decline", party=d.m(leader).party) if d.m(leader).party in d.w.invites.get(target, {}) else None
    inviters = [p for p in pids if d.m(p).party is None and p != target]
    for p in inviters[:MAX_INVITES + 1]:
        d.ask(p, "invite", player=target)
    assert len(d.w.invites[target]) <= MAX_INVITES


@pytest.mark.integration
def test_leader_disconnects_and_returns(world):
    d = Driver(world)
    a, ta = d.join()
    b, _ = d.join()
    c, _ = d.join()
    d.party(a, b)
    d.party(a, c)
    party = d.w.parties[d.m(a).party]
    d.w.disconnect(a)
    assert party.leader == b and party.members == [a, b, c]
    d.ask(b, "invite", player=d.join()[0])  # the new leader leads
    assert d.notices(b) == [] and len(d.w.invites) == 1
    pid, _ = d.join(ta)
    assert pid == a and party.leader == b and d.m(a).party == party.id
    d.w.disconnect(b)
    d.w.disconnect(c)
    assert party.leader == a


@pytest.mark.integration
def test_splitting_and_rejoining_a_party(world):
    d = Driver(world)
    a, _ = d.join()
    b, _ = d.join()
    d.party(a, b)
    d.through_hub_door(a, b)
    expedition = d.m(a).instance
    d.ask(b, "leave")
    assert d.room(b) is d.w.hub and d.notices(b)[-1] == "left_expedition" and d.m(a).instance == expedition
    d.through_hub_door(b)
    assert d.room(b) is d.w.hub and d.notices(b) == ["need_party"]  # no party, no expedition
    d.party(a, b)
    d.walk(b, -1, 0, 10)
    d.through_hub_door(b)
    assert d.m(b).instance == expedition  # the party's existing instance


@pytest.mark.integration
def test_nobody_enters_another_partys_instance(world):
    d = Driver(world)
    a, b, c = (d.join()[0] for _ in range(3))
    tc = d.join()  # (a fourth character, never used: the resume token below is c's)
    d.party(a, b)
    d.through_hub_door(a, b)
    expedition = d.m(a).instance
    d.ask(c, "create")
    d.through_hub_door(c)
    own = d.m(c).instance
    assert own != expedition and d.room(c).party == d.m(c).party != d.m(a).party
    d.ask(c, "leave")  # c's party ends, and with it c's instance
    assert d.room(c) is d.w.hub and own not in d.w.instances
    d.party(a, c)
    d.through_hub_door(c)
    assert d.m(c).instance == expedition  # a member now: the party's instance
    token = d.w.members[c].token
    d.w.disconnect(c)
    d.ask(a, "leave")
    d.ask(b, "leave")  # the party ends while c is away (c is the last member: it leaves when it expires)
    pid, _ = d.join(token)
    assert pid == c and d.m(c).party is not None and d.m(c).instance == expedition  # c alone still holds it
    d.ask(c, "leave")
    assert d.room(c) is d.w.hub and expedition not in d.w.instances and tc


@pytest.mark.integration
def test_capacity_and_instance_limits(world):
    d = Driver(world)
    pids = [d.join()[0] for _ in range(wire.MAX_PLAYERS)]
    with pytest.raises(wire.Invalid):
        d.join()
    for pid in pids:
        d.ask(pid, "create")
        d.through_hub_door(pid)
    rooms = [d.room(p).key for p in pids]
    assert rooms.count(R1) == MAX_INSTANCES - 1 and rooms.count(HUB) == 1 and len(d.w.instances) == MAX_INSTANCES
    assert d.notices(pids[-1]) == ["no_instance"]
    with pytest.raises(wire.Invalid):
        d.join("0" * 64)


# --- over sockets ----------------------------------------------------------------------------------


class Peer:
    """A minimal world client over a real socket (what mesh_net.world_client does, without a window)."""

    def __init__(self, reader, writer, world):
        self.reader, self.writer, self.world = reader, writer, world
        self.identities = {k: d.proto.identity for k, d in world.defs.items()}
        self.room = self.key = self.entity = self.state = self.party = None
        self.seq, self.notices = 0, []

    @classmethod
    async def open(cls, port, world, resume=None):
        reader, writer = await asyncio.open_connection("127.0.0.1", port, limit=wire.MAX_BYTES)
        writer.write(wire.encode({"v": 1, "type": "join", "resume": resume}))
        peer = cls(reader, writer, world)
        hello = await wire.read(reader)
        check_welcome(hello, world.identity)
        peer.player, peer.token = hello["player"], hello["resume"]
        return peer

    async def until(self, predicate, timeout=10.0):
        async def loop():
            while not predicate(self):
                msg = await wire.read(self.reader)
                check_frame(msg, self.identities)
                if msg["type"] == "enter":
                    self.room, self.key, self.entity, self.state = msg["room"], msg["key"], msg["entity"], msg["state"]
                elif msg["type"] == "room_state" and msg["room"] == self.room:
                    assert msg["state"]["scene"] == self.identities[self.key]
                    assert msg["state"]["tick"] > self.state["tick"]
                    self.state = msg["state"]
                elif msg["type"] == "party":
                    self.party = msg
                elif msg["type"] == "notice":
                    self.notices.append(msg["code"])
        await asyncio.wait_for(loop(), timeout)

    async def send(self, msg):
        self.writer.write(wire.encode(msg))
        await self.writer.drain()

    async def move(self, dx, dy, action=None):
        self.seq += 1
        frame = {"v": 1, "type": "input", "room": self.room, "entity": self.entity, "seq": self.seq, "dx": dx, "dy": dy}
        if action:
            frame["action"] = action
        await self.send(frame)

    def own(self):
        return next(r for r in self.state["players"] if r[0] == self.entity)

    async def close(self):
        self.writer.close()
        try:
            await asyncio.wait_for(self.writer.wait_closed(), 2)
        except (OSError, TimeoutError):
            self.writer.transport.abort()


async def walk_until(peers, dx, dy, done, timeout=15.0):
    """Each peer walks once per room state it receives, until ``done(peer)``."""
    async def one(p):
        while not done(p):
            await p.move(dx, dy)
            await p.until(lambda q, t=(p.room, p.state["tick"]): (q.room, q.state["tick"]) != t)
    await asyncio.wait_for(asyncio.gather(*(one(p) for p in peers)), timeout)


@pytest.mark.integration
def test_two_clients_travel_reconnect_and_return_over_sockets(files):
    async def run():
        world = make_world(files)
        server = WorldServer(world)
        port = await server.start(0)
        peers = []
        try:
            a = await Peer.open(port, world)
            b = await Peer.open(port, world)
            peers += [a, b]
            await asyncio.gather(a.until(lambda p: p.room and p.party), b.until(lambda p: p.room and p.party))
            await a.send({"v": 1, "type": "party", "op": "invite", "player": b.player})
            await b.until(lambda p: p.party["invites"])
            await b.send({"v": 1, "type": "party", "op": "accept", "party": b.party["invites"][0][0]})
            await a.until(lambda p: p.party["party"] and len(p.party["members"]) == 2)
            await walk_until([a, b], 1, 0, lambda p: p.key == R1)
            assert a.room == b.room and a.room.startswith(f"{R1}:") and a.own()[1:3] == [64.0, 160.0]
            await b.until(lambda p: len(p.state["players"]) == 2)
            # b drops; it resumes into the same expedition instance, where it stood, with its party.
            room, token, spot = b.room, b.token, b.own()[1:3]
            await b.close()
            await a.until(lambda p: len(p.state["players"]) == 1)
            b = await Peer.open(port, world, token)
            peers.append(b)
            await b.until(lambda p: p.room and p.party)
            assert b.room == room and b.own()[1:3] == spot and b.party["party"] == a.party["party"]
            # Both walk back to the hub up into Layer 1's door (above its arrival spot); the instance ends.
            await walk_until([a, b], 0, 1, lambda p: p.key == HUB)
            assert room not in world.instances and a.room == b.room == world.hub.id
            assert a.own()[1:3] == [704.0, 160.0]  # the hub's arrival marker
        finally:
            for p in peers:
                await p.close()
            await server.close()

    asyncio.run(run())


# --- measurements (descriptive, never a gate) ------------------------------------------------------


@pytest.mark.integration
def test_measure_world_tick_and_transfer_cost(world):
    d = Driver(world)
    pids = [d.join()[0] for _ in range(wire.MAX_PLAYERS)]
    for i in range(0, len(pids), 2):  # four parties of two, each in its own Layer 1
        d.party(pids[i], pids[i + 1])
        d.through_hub_door(pids[i], pids[i + 1])
    samples = []
    for _ in range(200):
        for i, pid in enumerate(pids):
            d.send(pid, (1, -1)[(d.w.tick // 20 + i) % 2], 0, action="attack")
        started = time.perf_counter()
        d.w.step()
        d.w.deliver()
        samples.append((time.perf_counter() - started) * 1000)
    samples.sort()
    a, _ = d.join() if len(d.w.members) < wire.MAX_PLAYERS else (None, None)
    transfers = []
    pid = pids[0]
    for _ in range(20):
        d.place(pid, 640.0, 256.0) if d.room(pid).key == HUB else d.place(pid, 128.0, 256.0)
        start = time.perf_counter()
        d.walk(pid, 1 if d.room(pid).key == HUB else -1, 0, 6)
        transfers.append((time.perf_counter() - start) * 1000 / 6)
    print(f"world tick, 8 players in 5 rooms: median {samples[100]:.2f} ms, p95 {samples[190]:.2f} ms; "
          f"ticks with a transfer: mean {sum(transfers) / len(transfers):.2f} ms")
    assert a is None
