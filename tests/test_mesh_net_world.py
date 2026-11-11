"""N7: many Studio-authored rooms, transitions and parties under one graphics-free authority (mesh_net.world)."""

import asyncio
import json
import subprocess
import sys
import time

import pytest

from mesh_net import protocol as wire
from mesh_net.scene_room import Unsupported, disposable_project
from mesh_net.server import WorldServer
from mesh_net.world import (
    EXPEDITION_FILES,
    MAX_INSTANCES,
    MAX_INVITES,
    MAX_PARTY,
    RETAIN_TICKS,
    TransferResult,
    World,
    check_frame,
    check_welcome,
    expedition_files,
    welcome,
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
    """Nothing in them is multiplayer-specific: the world file is Studio's (keys, paths, its own ``tags`` field), and
    the engine's strict loader keeps every room's objects, doors and arrival markers."""
    from engine.scene_loader import SceneLoader

    with disposable_project(files) as root:
        world = json.loads((root / "packs/core_regions/worlds/main.json").read_text(encoding="utf-8"))
        scenes = {key: SceneLoader().load_scene(str(root / path), strict=True) for key, path in SCENES.items()}
    assert {k: v["path"] for k, v in world["scenes"].items()} == SCENES and world["start_scene"] == HUB
    assert {k: v["tags"] for k, v in world["scenes"].items()} == {HUB: ["start"], R1: ["expedition"], R2: ["expedition"]}
    assert [e["tag"] for e in scenes[R1]["entities"] if e.get("tag") in ("door", "spawn_point")] == ["door", "spawn_point"] * 2
    player = scenes[R2]["entities"][0]
    assert [b["type"] for b in player["behaviours"]] == ["PlayerController", "CameraFollow", "Animator", "Combat"]


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
    # b names a's room and a's entity, with a sequence a's room would accept: dropped (it is not b's room).
    d.place(a, 568.0, 352.0, facing=0)  # beside a's bandit, facing it: an accepted "attack" would hit
    hp = ra.room.enemies[BANDIT].state.hp
    before = d.at(a)
    d.seq[b] = d.seq[a] + 100
    d.send(b, 1, 0, action="attack", room=ra.id, entity=d.m(a).eid)
    d.step()
    assert d.at(a) == before and ra.room.enemies[BANDIT].state.hp == hp and ra.room.players[d.m(a).eid].seq < d.seq[b]
    assert not rb.room.used
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
    open_gate(d, a)
    d.to_layer_2(a)
    d.to_layer_2(b)
    r2 = d.m(a).instance
    assert d.room(a).key == R2 and r1 in d.w.instances  # the party is still in its expedition
    for pid in (a, b):  # back up to Layer 1 through Layer 2's door: as they left it
        d.place(pid, 128.0, 256.0)
    d.walk_in(-1, a, b)
    assert d.m(a).instance == r1 and GATE1 in d.room(a).room.snapshot()["open"] and r2 in d.w.instances
    for pid in (a, b):  # back to the hub through Layer 1's door
        d.place(pid, 128.0, 256.0)
    d.walk_in(-1, a)
    assert d.room(a) is d.w.hub and r1 in d.w.instances  # b is still inside
    d.walk_in(-1, b)
    assert d.room(b) is d.w.hub and r1 not in d.w.instances and r2 not in d.w.instances
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
def test_party_size_and_invitation_bounds(files):
    d = Driver(make_world(files))
    leader, *rest = (d.join()[0] for _ in range(MAX_PARTY + 1))
    for pid in rest[:-1]:
        d.party(leader, pid)
    d.ask(leader, "invite", player=rest[-1])
    d.ask(rest[-1], "accept", party=d.m(leader).party)
    assert d.notices(rest[-1]) == ["party_full"] and len(d.w.parties[d.m(leader).party].members) == MAX_PARTY
    d = Driver(make_world(files))
    target, *leaders = (d.join()[0] for _ in range(wire.MAX_PLAYERS))
    for pid in leaders:
        d.ask(pid, "invite", player=target)
    assert len(d.w.invites[target]) == MAX_INVITES
    assert [d.notices(p) for p in leaders] == [[]] * MAX_INVITES + [["busy"]] * (len(leaders) - MAX_INVITES)
    assert len(d.w.parties) == MAX_INVITES  # a refused invitation creates no party


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
    """Descriptive only (printed, never a gate): one world tick with 8 players in 5 rooms, and the tick in which a
    player walks through a door."""
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
    pid, transfers = pids[0], []
    for _ in range(20):  # one tick's walk from beside a door into it: Layer 1 to the hub and back
        to_hub = d.room(pid).key == R1
        d.place(pid, 116.0 if to_hub else 652.0, 256.0)
        d.send(pid, -1 if to_hub else 1, 0)
        started = time.perf_counter()
        d.w.step()
        d.w.deliver()
        transfers.append((time.perf_counter() - started) * 1000)
        assert d.room(pid).key == (HUB if to_hub else R1)
    transfers.sort()
    print(f"world tick, 8 players in 5 rooms: median {samples[100]:.2f} ms, p95 {samples[190]:.2f} ms; "
          f"tick with a transfer: median {transfers[10]:.2f} ms, max {transfers[-1]:.2f} ms")


# --- guards the independent review found unproven ---------------------------------------------------


@pytest.mark.integration
def test_a_resume_credential_works_once(world):
    d = Driver(world)
    a, first = d.join()
    with pytest.raises(wire.Invalid):
        d.join(first)  # not while its session is live
    d.w.disconnect(a)
    pid, second = d.join(first)
    assert pid == a and second != first
    d.w.disconnect(a)
    with pytest.raises(wire.Invalid):
        d.join(first)  # spent
    assert d.join(second)[0] == a


@pytest.mark.integration
def test_invitations_expire_and_follow_their_inviter(world):
    from mesh_net.world import INVITE_TICKS

    d = Driver(world)
    a, b, c = (d.join()[0] for _ in range(3))
    d.ask(a, "invite", player=b)
    d.step(INVITE_TICKS)
    d.ask(b, "accept", party=d.m(a).party)
    assert d.notices(b) == ["no_invite"] and d.m(b).party is None
    d.party(a, c)
    d.ask(a, "invite", player=b)
    d.ask(a, "leave")  # the inviter leaves the party: its invitation goes with it
    d.ask(b, "accept", party=d.m(c).party)
    assert d.notices(b) == ["no_invite"] and d.m(b).party is None


@pytest.mark.integration
def test_accepting_while_the_leader_is_away_hands_over_the_lead(world):
    d = Driver(world)
    a, b, c = (d.join()[0] for _ in range(3))
    d.ask(a, "invite", player=b)
    d.w.disconnect(a)
    d.ask(b, "accept", party=d.m(a).party)
    party = d.w.parties[d.m(b).party]
    assert party.members == [a, b] and party.leader == b
    d.ask(b, "invite", player=c)
    assert d.notices(b) == []


@pytest.mark.integration
def test_a_full_destination_refuses_and_keeps_the_player_where_they_stood(world):
    d = Driver(world)
    a, b = d.join()[0], d.join()[0]
    d.party(a, b)
    d.through_hub_door(a)
    expedition = d.room(a).room
    while len(expedition.players) < wire.MAX_PLAYERS:  # (filled by hand: eight connections can't fill a room)
        expedition.join()
    d.through_hub_door(b)
    assert d.room(b) is d.w.hub and d.notices(b) == ["room_full"] and d.m(b).eid in d.w.hub.room.players


@pytest.mark.integration
def test_a_failed_join_puts_the_player_back(world):
    d = Driver(world)
    a, _ = d.join()
    d.ask(a, "create")
    original = World._enter
    calls = []

    def failing(self, m, inst, player):
        calls.append(inst.key)
        if inst.key == R1:
            raise OSError("broken destination")
        return original(self, m, inst, player)

    def joined_then_failing(self, m, inst, player):  # (fails after the room took the avatar)
        calls.append(inst.key)
        if inst.key == R1:
            inst.room.join(player)
            raise OSError("broken destination")
        return original(self, m, inst, player)

    World._enter = failing
    try:
        d.through_hub_door(a)
    finally:
        World._enter = original
    assert calls[0] == R1 and d.room(a) is d.w.hub and d.m(a).eid in d.w.hub.room.players
    assert d.notices(a) == ["transfer_failed"]
    door = next(x for x in d.w.defs[HUB].doors if x.target == R1)
    World._enter = joined_then_failing
    try:
        result = d.w.transfer(d.m(a), d.w.hub, door)  # (called directly: before the tick's cleanup could hide it)
    finally:
        World._enter = original
    target = d.w.instances[d.w.party_rooms[(d.m(a).party, R1)]]
    assert result is TransferResult.FAILED and not target.room.players and d.room(a) is d.w.hub  # no orphan
    assert d.notices(a) == ["transfer_failed"]
    d.w.disconnect(a)  # no ghost: the player is somewhere, so leaving works
    assert not d.m(a).online


@pytest.mark.integration
def test_malformed_requests_raise_invalid_only(world):
    d = Driver(world)
    a, _ = d.join()
    for bad in ({"op": []}, {"op": {}}, {"op": None}):
        with pytest.raises(wire.Invalid):
            d.w.party(a, {"v": 1, "type": "party", **bad})
    for room in ([], 5, None, "start:1:2", "START:1"):
        with pytest.raises(wire.Invalid):
            d.w.input(a, {"v": 1, "type": "input", "room": room, "entity": 1, "seq": 1, "dx": 0, "dy": 0})


@pytest.mark.integration
def test_clients_reject_malformed_frames(world):
    ids = {k: d.proto.identity for k, d in world.defs.items()}
    hub = world.hub.room.snapshot()
    world.hub.room.join()
    hub_with_one = world.hub.room.snapshot()
    good_enter = {"v": 1, "type": "enter", "room": "start:1", "key": HUB, "entity": 1, "state": hub_with_one}
    check_frame(good_enter, ids)
    party = {"v": 1, "type": "party", "you": 1, "party": None, "leader": None, "members": [], "invites": [], "nearby": []}
    check_frame(party, ids)
    bad = [
        {**good_enter, "key": [HUB]},
        {**good_enter, "key": R1},  # the room id names another room
        {**good_enter, "entity": 2},  # not its own avatar
        {**good_enter, "state": hub},  # no players at all
        {**good_enter, "state": {**hub_with_one, "scene": "0" * 64}},  # another scene
        {**party, "members": [[1, True, [HUB]]]},
        {**party, "members": [[1, True, "nowhere"]]},
        {"v": 1, "type": "notice", "code": ["busy"]},
        {"v": 1, "type": "notice", "code": "teleported"},
        {"v": 1, "type": "room_state", "room": "start", "state": hub_with_one},
        {"v": 1, "type": "welcome"},
    ]
    for frame in bad:
        with pytest.raises(wire.Invalid):
            check_frame(frame, ids)
    with pytest.raises(wire.Invalid):
        check_welcome(welcome("0" * 32, 1, "a" * 64, "b" * 64), world.identity)  # another world


@pytest.mark.integration
def test_the_client_applies_only_its_own_rooms_frames_in_order(world):
    """world_client.WorldArena.on_frame: after an enter, a state of another room is dropped (it was in flight), and
    within its room a state must be newer than the last."""
    from types import SimpleNamespace

    from mesh_net.world_client import WorldArena

    ids = {k: d.proto.identity for k, d in world.defs.items()}
    world.hub.room.join()
    state = world.hub.room.snapshot()
    arena = SimpleNamespace(identities=ids, room=None, key=None, entity=None, state=None, playback=None,
                            pending=None, phase="loading", party=None, notice=None)
    WorldArena.on_frame(arena, {"v": 1, "type": "enter", "room": "start:1", "key": HUB, "entity": 1, "state": state}, 0.0)
    assert arena.room == "start:1" and arena.pending is not None
    WorldArena.on_frame(arena, {"v": 1, "type": "room_state", "room": "start:7", "state": {**state, "tick": 99}}, 0.1)
    assert arena.state["tick"] == state["tick"]  # another room's: dropped
    world.hub.room.step()
    newer = world.hub.room.snapshot()
    WorldArena.on_frame(arena, {"v": 1, "type": "room_state", "room": "start:1", "state": newer}, 0.1)
    assert arena.state["tick"] == newer["tick"]
    with pytest.raises(wire.Invalid):
        WorldArena.on_frame(arena, {"v": 1, "type": "room_state", "room": "start:1", "state": newer}, 0.2)


@pytest.mark.integration
def test_a_failing_world_closes_the_server_instead_of_freezing(files, caplog):
    async def run():
        world = make_world(files)
        server = WorldServer(world)
        port = await server.start(0)
        try:
            peer = await Peer.open(port, world)
            await peer.until(lambda p: p.room)
            world.step = lambda: (_ for _ in ()).throw(RuntimeError("deliberate"))
            with pytest.raises((asyncio.IncompleteReadError, ConnectionError, wire.Invalid)):
                await peer.until(lambda p: False, timeout=5)
            with pytest.raises(OSError):
                await Peer.open(port, world)
            await peer.close()
        finally:
            await server.close()

    asyncio.run(run())
    assert "the world failed" in caplog.text


@pytest.mark.integration
def test_the_server_process_ends_when_its_world_fails(files):
    """mesh_net.server.serve (what ``python -m mesh_net.server`` runs) returns with the world's error instead of
    staying alive with no listener and no clock."""
    from mesh_net.server import serve

    async def run():
        world = make_world(files)
        world.step = lambda: (_ for _ in ()).throw(RuntimeError("deliberate"))
        await asyncio.wait_for(serve(0, world, WorldServer), 5)

    with pytest.raises(RuntimeError, match="deliberate"):
        asyncio.run(run())


@pytest.mark.integration
def test_leaving_ends_the_session_even_if_a_cancellation_is_swallowed(files, monkeypatch):
    """F2 (or closing the window) cancels the world client's session. On Python 3.11, asyncio.wait_for returns the
    inner result instead of raising when it is cancelled just as that result arrives (fixed in 3.12), so a send loop
    can miss its cancellation. The session must still close its connection, so the server sees the player leave."""
    from types import SimpleNamespace

    import mesh_net.world_client as world_client

    armed = [True]

    async def swallowing_wait_for(aw, timeout):  # 3.11's race, every time: the cancel lands while it waits
        if not armed[0]:
            return await asyncio.wait_for(aw, timeout)
        fut = asyncio.ensure_future(aw)
        try:
            await asyncio.sleep(0.2)
            return await asyncio.shield(fut)
        except asyncio.CancelledError:
            return await fut  # (3.11: the inner result arrived, so the cancellation is dropped)

    monkeypatch.setattr(world_client, "asyncio", SimpleNamespace(**{**vars(asyncio), "wait_for": swallowing_wait_for}))
    keys = SimpleNamespace(**{name: i for i, name in enumerate(("W", "UP", "S", "DOWN", "A", "LEFT", "D", "RIGHT"))})
    window = SimpleNamespace(push_handlers=lambda **handlers: None)

    async def run():
        world = make_world(files)
        server = WorldServer(world)
        port = await server.start(0)
        session = None
        try:
            with disposable_project(files, scaffold=False) as root:
                arena = world_client.WorldArena(window, SimpleNamespace(key=keys), root, "unused")
            arena.phase = "connecting"
            session = asyncio.create_task(arena.session(port))
            assert await _within(5, lambda: any(m.online for m in world.members.values()) and arena.room)
            arena.shown = arena.room  # (as the window does once it shows the room: the send loop now sends input)
            await asyncio.sleep(0.3)
            session.cancel()
            # (well within the server's 5 s read timeout: the leave comes from the closed connection, not silence)
            left = await _within(2, lambda: not any(m.online for m in world.members.values()))
            assert left, f"the server never saw the player leave; client trace {list(arena.trace)}"
            await asyncio.wait({session}, timeout=5)
            assert session.done() and arena.phase == "disconnected" and "closed" in [e for _, e in arena.trace]
        finally:
            armed[0] = False
            await server.close()  # (unblocks a session that hung: its connection ends)
            if session is not None:
                await asyncio.wait({session}, timeout=5)

    asyncio.run(run())


async def _until(predicate):
    while not predicate():
        await asyncio.sleep(0.02)


async def _within(seconds, predicate):
    """Whether ``predicate`` comes true within ``seconds`` (never cancels anything: a hung task stays visible)."""
    deadline = asyncio.get_running_loop().time() + seconds
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            return False
        await asyncio.sleep(0.02)
    return True


# --- resource guards (from the fresh independent review: each fails with its guard removed) -------------


@pytest.mark.integration
def test_retained_characters_count_towards_the_cap(world):
    from mesh_net.world import MAX_CHARACTERS

    d = Driver(world)
    for _ in range(MAX_CHARACTERS // wire.MAX_PLAYERS):
        pids = [d.join()[0] for _ in range(wire.MAX_PLAYERS)]
        for pid in pids:
            d.w.disconnect(pid)  # retained for 30 s
    assert len(d.w.members) == MAX_CHARACTERS
    with pytest.raises(wire.Invalid, match="capacity"):
        d.join()


@pytest.mark.integration
def test_notices_and_history_stay_bounded(world):
    d = Driver(world)
    a, _ = d.join()
    for _ in range(50):
        d.ask(a, "invite", player=a)  # refused each time: a notice
    assert len(d.w.members[a].outbox) <= 8
    for i in range(40):
        pid, _ = d.join()
        d.w.disconnect(pid)
        if i % 10 == 9:
            d.step(RETAIN_TICKS + 1)  # (the retained characters expire: room for more)
    assert len(d.w.history) == d.w.history.maxlen == 64


@pytest.mark.integration
def test_invitations_end_with_their_invitee_or_their_party(world):
    d = Driver(world)
    a, b, c = (d.join()[0] for _ in range(3))
    d.ask(a, "invite", player=b)
    d.w.disconnect(b)
    assert b not in d.w.invites  # an away player holds no invitations
    d.ask(a, "invite", player=c)
    assert d.w.invites[c]
    d.ask(a, "leave")  # a's party ends with its last member
    assert all(not pending for pending in d.w.invites.values())


@pytest.mark.integration
def test_the_server_limits_requests_per_tick(files):
    async def run():
        world = make_world(files)
        server = WorldServer(world)
        port = await server.start(0)
        try:
            peer = await Peer.open(port, world)
            await peer.until(lambda p: p.room and p.party)
            world.step = lambda: None  # (the tick stands still: every request below lands in one tick)
            for _ in range(9):
                await peer.send({"v": 1, "type": "party", "op": "leave"})
            assert await _within(3, lambda: not any(m.online for m in world.members.values()))
            await peer.close()
        finally:
            await server.close()

    asyncio.run(run())


@pytest.mark.integration
def test_pressing_e_before_a_new_room_shows_does_not_ask_the_old_room():
    """Just after an enter, the window still shows the last room until its next frame. E then must not look the new
    room's drops up in the old room's view (that raised KeyError out of the window's event dispatch)."""
    from types import SimpleNamespace

    from mesh_net.world_client import WorldArena

    def old_view_lookup(x, y, state):
        raise KeyError(state["drops"][0])

    key = SimpleNamespace(E=1, SPACE=2, P=3, I=4, Y=5, N=6, L=7, ESCAPE=8, F2=9, R=10)
    state = {"players": [[1, 100.0, 100.0, 0]], "drops": [GUARDIAN]}
    arena = SimpleNamespace(arcade=SimpleNamespace(key=key), directions={}, connected=True, action_keys=set(),
                            action=None, phase="loading", request=None, note=lambda event: None, state=state,
                            entity=1, view=SimpleNamespace(near_drop=old_view_lookup), shown="start:1",
                            room=f"{R2}:3", _own=lambda: state["players"][0])
    assert WorldArena.press(arena, key.E, 0) is True and arena.action == "use"
