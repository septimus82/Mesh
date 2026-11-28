"""M4-5 (owner decision of 2026-11-25 on OD5): bounded server-side lag compensation for the co-op PvE prototype.

An attack's ``view_tick`` (Playback's cursor on the frame its window showed) has the authority judge its targets where
they were then, from the room instance's own history, and the attacker where it stands now:

- enemies only, never the attacker; at most REWIND_CAP ticks (300 ms) back, clamped; never ahead of the tick, never
  before the attacker joined this room instance, never another identity's pose; missing history judges now (never a
  hit invented); damage, death and drops are now's; a target dead now is never hit through history;
- the same rule a window shows an enemy by (playback.between) and the same hit test (_strike: shapes and same_level,
  so floors, stairs and bridge decks) at the rewound pose; later hitbox ticks keep the view's lag;
- the history is bounded (REWIND_CAP + 1 ticks), deterministic, kept per room instance (each N7 instance its own).
"""

from __future__ import annotations

import copy
import json
from argparse import Namespace
from typing import Any

import pytest

from engine.combat_model import TargetState
from engine.physics_model import Aabb, entity_shape, shape_aabb
from mesh_net import protocol as wire
from mesh_net.playback import Playback
from mesh_net.scene_room import REWIND_CAP, Body, Enemy, Player, SceneRoom, disposable_project
from mesh_net.server import rewind_from
from tests.test_mesh_net_moving_enemies import SCENE, bandit, with_entities
from tooling.m4_latency_probe import BANDIT, crossing_files

pytestmark = pytest.mark.integration  # (builds projects in folders, loads rooms from files)

# The bandit walking east and west on the crossing's open ground, fast (150 px/s authored, 4.4 px a tick here).
GROUND = {"route": [[552.0, 104.0, 0.0], [664.0, 104.0, 0.0]], "speed": 150.0, "wait": 0.0}
# Up and down the west stairs, through same_level's 1.5 m reach of a player on the ground beside them (the probe's).
STAIRS = {"route": [[328.0, 152.0, 4.0], [328.0, 264.0, 60.0]], "speed": 70.0, "wait": 0.0}
# A diagonal over the open ground (x/y never whole hundredths of a pixel).
DIAGONAL = {"route": [[552.0, 104.0, 0.0], [640.0, 150.0, 0.0]], "speed": 70.0, "wait": 0.0}
# Along the bridge deck, 2 m up.
DECK = {"route": [[472.0, 384.0, 64.0], [584.0, 384.0, 64.0]], "speed": 70.0, "wait": 0.0}


@pytest.fixture(scope="module")
def files() -> dict[str, bytes]:
    return crossing_files()


def routed(files: dict[str, bytes], route: dict[str, Any], x: float, y: float, z: float = 0.0, **kw: Any) -> SceneRoom:
    """The crossing with the bandit at (x, y, z) walking ``route``; ``kw``: SceneRoom's own settings (rewind)."""
    with disposable_project(with_entities(files, bandit(x, y, z, route=route)), scaffold=False) as root:
        room = SceneRoom(root / SCENE, root, **kw)
    room.enemies[BANDIT].state = TargetState(hp=1000.0, max_hp=1000.0)
    return room


def ground_room(files: dict[str, bytes], **kw: Any) -> SceneRoom:
    return routed(files, GROUND, 552.0, 122.0, **kw)


def shape(room: SceneRoom, pose: tuple[Any, ...]) -> Aabb:
    """The bandit's shape (as _strike tests it) at ``pose`` (x, y, elevation px, ...)."""
    e = room.enemies[BANDIT].body
    return shape_aabb(entity_shape(Body(pose[0], pose[1], e.width, e.height, {**e.mesh_entity_data, "elevation": pose[2]})))


def pose(room: SceneRoom, tick: int) -> tuple[Any, ...]:
    """The bandit's (x, y, elevation, floor) after ``tick``, as the room's history keeps it."""
    entry = dict(room.history)[tick][BANDIT]
    assert entry[0] is room.enemies[BANDIT]
    return entry[1:]


def stand(room: SceneRoom, eid: int, box: tuple[float, float], facing: int = 0, z: float = 0.0) -> Player:
    """Put player ``eid`` where its hitbox (facing ``facing``) is centred at ``box``, at elevation ``z`` px."""
    from mesh_net.scene_room import FACINGS

    p = room.players[eid]
    fx, fy = FACINGS[facing]
    p.body.center_x, p.body.center_y, p.facing = box[0] - fx * room.reach, box[1] - fy * room.reach, facing
    p.body.mesh_entity_data["elevation"] = z
    return p


def edge(room: SceneRoom, at: tuple[Any, ...]) -> tuple[float, float]:
    """A hitbox centre (facing east) overlapping the bandit's shape at pose ``at`` by 1 px, from the west."""
    s = shape(room, at)
    return s.x - s.w / 2 - room.hitbox / 2 + 1.0, s.y


def hits(room: SceneRoom, eid: int, view: Any) -> bool:
    """Whether an attack by ``eid`` with ``view`` (its view tick, or None), made now, hits the bandit on its first tick.
    On a copy of the room, so each trial starts alike."""
    trial = copy.deepcopy(room, {id(room.world): room.world})
    before = trial.enemies[BANDIT].hit_seq
    trial._attack(trial.players[eid], view)
    return trial.enemies[BANDIT].hit_seq > before


def walking_east(room: SceneRoom, ticks: int = 12) -> None:
    for _ in range(ticks):
        room.step()
    assert pose(room, room.tick)[0] > pose(room, room.tick - REWIND_CAP)[0] + 20.0, "walking east, fast"


def test_a_view_judges_the_targets_where_the_window_showed_them(files: dict[str, bytes]) -> None:
    """The bandit walked east since the view: a hitbox on where the window showed it then hits with that view, misses
    without one (where it is now), and misses with lag compensation off. The history keeps each tick's pose exactly as
    that tick's snapshot row carries it."""
    room = ground_room(files)
    eid = room.join()
    rows = []
    for _ in range(12):
        room.step()
        rows.append((room.tick, next(r for r in room.snapshot()["enemies"] if r[0] == BANDIT)))
    assert all(tuple(r[3:7]) == pose(room, t) for t, r in rows[-REWIND_CAP - 1:]), "the snapshot rows' poses"
    view = room.tick - 4
    stand(room, eid, edge(room, pose(room, view)))
    assert hits(room, eid, view), "where the window showed it: a hit"
    assert hits(room, eid, float(view)), "(a view is a number)"
    assert not hits(room, eid, None), "no view: judged where it is now, a miss"
    off = ground_room(files, rewind=False)
    off_eid = off.join()
    for _ in range(12):
        off.step()
    assert pose_now(off) == pose_now(room), "the same walk"
    stand(off, off_eid, edge(room, pose(room, view)))
    assert not off.history and not hits(off, off_eid, view), "lag compensation off: no history, judged now"


def test_the_attacker_is_never_rewound(files: dict[str, bytes]) -> None:
    """Rewinding moves only the enemies. The attacker stood, from before the view tick, where its hitbox lay on the
    bandit's pose at that tick, then walked two steps west. Its attack judged with that very view (the bandit put back
    to the pose the hitbox was placed against), facing east as then, is made where the attacker stands now: a miss. Put
    back where it stood at the view, the same attack hits: the miss is the attacker's own move, so an attacker rewound
    to the view would hit (#626 review: walking 6 steps judged a moment other than the one the hitbox was placed
    against, where the bandit had walked on, so a rewound attacker missed too)."""
    room = ground_room(files)
    eid = room.join()
    trial = copy.deepcopy(room, {id(room.world): room.world})  # (the same walk: deterministic, tested below)
    walking_east(trial)
    view = trial.tick - 4
    box = edge(trial, pose(trial, view))
    while room.tick < view - 2:
        room.step()
    p = stand(room, eid, box)  # (standing there from before the view tick)
    while room.tick < trial.tick:
        room.step()
    assert pose(room, view) == pose(trial, view), "the same walk, the attacker standing by"
    assert hits(room, eid, view), "where it stood at the view: a hit"
    then = p.body.center_x
    for seq in (1, 2):  # (two steps west, through the authority's own steps)
        room.input(eid, wire.input_frame(eid, seq, -1, 0, room.tick + 1))
        room.step()
    assert then - p.body.center_x == pytest.approx(2 * room.step_px)
    p.facing = 0  # (facing east again, as at the view: only where it stands differs)
    assert room.tick - REWIND_CAP == view, "the very view the hitbox was placed against, within the cap"
    assert not hits(room, eid, view), "the hitbox is made where the attacker stands now"
    p.body.center_x = then
    assert hits(room, eid, view), "(control) back where it stood at the view: a hit, so the miss is its own move"


def test_a_view_ahead_of_the_tick_is_judged_now(files: dict[str, bytes]) -> None:
    """A view tick the room hasn't reached (no honest window has one) is never a time to judge at: judged where the
    targets are now, and counted (future_views)."""
    room = ground_room(files)
    eid = room.join()
    walking_east(room)
    stand(room, eid, edge(room, pose(room, room.tick)))
    for view in (room.tick + 1, room.tick + 0.5, room.tick + 100):
        before = room.future_views
        trial = copy.deepcopy(room, {id(room.world): room.world})
        trial._attack(trial.players[eid], view)
        assert trial.enemies[BANDIT].hit_seq == 1, f"{view}: judged now, where it is in reach"
        assert trial.future_views == before + 1, "counted"
    stand(room, eid, edge(room, pose(room, room.tick - 4)))
    assert not hits(room, eid, room.tick + 1), "not in reach now: a miss, whatever the claim"


def test_the_rewind_stops_at_300_ms(files: dict[str, bytes]) -> None:
    """REWIND_CAP (6 ticks, 300 ms): a view exactly that old is judged then; an older one is clamped to it (counted
    in clamped_views), never judged further back. The history keeps no more than REWIND_CAP + 1 ticks."""
    assert REWIND_CAP == 6
    room = ground_room(files)
    eid = room.join()
    walking_east(room, 20)
    assert len(room.history) == REWIND_CAP + 1 and [t for t, _ in room.history] == list(
        range(room.tick - REWIND_CAP, room.tick + 1)), "bounded: the last 7 ticks"
    cap = room.tick - REWIND_CAP
    stand(room, eid, edge(room, pose(room, cap)))
    trial = copy.deepcopy(room, {id(room.world): room.world})
    trial._attack(trial.players[eid], cap)
    assert trial.enemies[BANDIT].hit_seq == 1 and trial.clamped_views == 0, "exactly 300 ms: judged then"
    for view in (cap - 0.5, cap - 4, 0):
        trial = copy.deepcopy(room, {id(room.world): room.world})
        trial._attack(trial.players[eid], view)
        assert trial.enemies[BANDIT].hit_seq == 1 and trial.clamped_views == 1, f"{view}: clamped to 300 ms back"


def test_the_clamp_judges_the_oldest_pose_it_allows_not_an_older_one(files: dict[str, bytes]) -> None:
    """A view 10 ticks back: judged at 6 ticks back. A hitbox on where the bandit was 10 ticks ago misses (an
    unbounded rewind would hit it); one on where it was 6 ticks ago hits."""
    room = ground_room(files)
    eid = room.join()
    walking_east(room, 14)
    history = {t: pose(room, t) for t, _ in room.history}
    old = room.tick - 10
    room_far = ground_room(files)  # (a twin that remembers 10 ticks back: what an unbounded history would hold)
    far_eid = room_far.join()
    room_far.history = type(room_far.history)(maxlen=None)
    for _ in range(14):
        room_far.step()
    assert dict(room_far.history)[room.tick - REWIND_CAP][BANDIT][1:] == history[room.tick - REWIND_CAP], "twins"
    assert history[room.tick - REWIND_CAP][0] - dict(room_far.history)[old][BANDIT][1] > 10.0, "4 ticks apart"
    stand(room, eid, edge(room, dict(room_far.history)[old][BANDIT][1:]))
    assert not hits(room, eid, old), "10 ticks back is beyond the cap: not there"
    stand(room, eid, edge(room, history[room.tick - REWIND_CAP]))
    assert hits(room, eid, old), "clamped to 6 ticks back: there"
    stand(room_far, far_eid, edge(room, dict(room_far.history)[old][BANDIT][1:]))
    assert not hits(room_far, far_eid, old), "the cap holds even with more history kept"


def test_no_view_from_before_the_attacker_joined_this_room(files: dict[str, bytes]) -> None:
    """A transfer or a resume joins anew: a view tick older than the join was never this player's view of this room
    instance; judged now (counted: unseen_views). From the join on, it is judged then."""
    room = ground_room(files)
    eid = room.join()
    walking_east(room, 8)
    player = room.leave(eid)
    eid = room.join(player)
    assert room.players[eid].joined == room.tick
    for _ in range(4):
        room.step()
    joined = room.players[eid].joined
    stand(room, eid, edge(room, pose(room, joined - 1)))
    trial = copy.deepcopy(room, {id(room.world): room.world})
    trial._attack(trial.players[eid], joined - 1)
    assert trial.enemies[BANDIT].hit_seq == 0 and trial.unseen_views == 1, "before it joined: judged now, a miss"
    stand(room, eid, edge(room, pose(room, joined)))
    assert hits(room, eid, joined), "from its join: judged then"


def test_another_identity_under_the_same_id_is_judged_now(files: dict[str, bytes]) -> None:
    """History is kept with the Enemy it belongs to: a new Enemy under the same id (a respawn, an id reused) never
    takes the old one's poses; it is judged where it is now."""
    room = ground_room(files)
    eid = room.join()
    walking_east(room)
    view = room.tick - 4
    stand(room, eid, edge(room, pose(room, view)))
    old = room.enemies[BANDIT]
    room.enemies[BANDIT] = Enemy(copy.deepcopy(old.body), TargetState(hp=1000.0, max_hp=1000.0), old.solid)
    assert not hits(room, eid, view), "another identity: judged now"
    room.enemies[BANDIT] = old
    assert hits(room, eid, view)


def test_missing_history_never_invents_a_hit(files: dict[str, bytes]) -> None:
    """A view whose ticks history doesn't hold (only one of the two around a fraction, or none) judges now: nothing is
    made up from the nearest pose kept."""
    room = ground_room(files)
    eid = room.join()
    walking_east(room)
    oldest = room.history[0][0]
    stand(room, eid, edge(room, pose(room, oldest)))
    assert hits(room, eid, oldest), "the oldest kept tick itself"
    stand(room, eid, edge(room, pose(room, oldest + 1)))
    assert hits(room, eid, oldest + 1)
    room.history.popleft()  # (that tick no longer kept; the next is, where this hitbox would reach it)
    assert not hits(room, eid, oldest + 0.5), "half a tick before the oldest kept: judged now, never its neighbour"
    assert not hits(room, eid, oldest), "no pose for that tick: judged now, never the nearest kept"
    room.history.clear()
    stand(room, eid, edge(room, pose_now(room)))
    assert hits(room, eid, room.tick - 2), "no history at all: judged now, where it is in reach"


def pose_now(room: SceneRoom) -> tuple[Any, ...]:
    b = room.enemies[BANDIT].body
    return b.center_x, b.center_y, b.mesh_entity_data.get("elevation", 0.0), b.mesh_hd2d_floor


def test_a_target_dead_now_is_never_hit_through_history(files: dict[str, bytes]) -> None:
    """Alive where the window showed it, dead since: no hit, no damage. A target hit once by a hitbox is not hit again
    by its later ticks."""
    room = ground_room(files)
    eid = room.join()
    walking_east(room)
    view = room.tick - 4
    stand(room, eid, edge(room, pose(room, view)))
    enemy = room.enemies[BANDIT]
    enemy.state = TargetState(hp=0.0, max_hp=1000.0, dead=True)
    trial = copy.deepcopy(room, {id(room.world): room.world})
    trial._attack(trial.players[eid], view)
    assert trial.enemies[BANDIT].hit_seq == 0 and trial.enemies[BANDIT].state.hp == 0.0, "dead now: never hit"
    enemy.state = TargetState(hp=1000.0, max_hp=1000.0)
    p = room.players[eid]
    room._attack(p, view)
    assert enemy.hit_seq == 1 and enemy.state.hp < 1000.0
    for _ in range(room.lifetime):
        room.step()
    assert enemy.hit_seq == 1, "once per hitbox"


def test_later_hitbox_ticks_keep_the_views_lag(files: dict[str, bytes], monkeypatch: pytest.MonkeyPatch) -> None:
    """OD10's hitbox checks on 3 ticks: each judges the targets the same time behind as its first (the window's view
    goes on lagging as much), never now and never the first tick's pose again. Without a view it never rewinds."""
    room = ground_room(files)
    eid = room.join()
    walking_east(room)
    seen: list[float] = []
    rewound = room._rewound
    monkeypatch.setattr(room, "_rewound", lambda at: (seen.append(at), rewound(at))[1])
    made = room.tick
    room._attack(room.players[eid], made - 3.5)
    for _ in range(room.lifetime):
        room.step()
    assert seen == [made - 3.5, made - 2.5, made - 1.5], seen
    seen.clear()
    room._attack(room.players[eid], None)
    for _ in range(room.lifetime):
        room.step()
    assert seen == []


def test_a_fractional_view_is_the_pose_the_window_drew(files: dict[str, bytes]) -> None:
    """The window shows an enemy between two states (Playback.enemies, from the rows' 0.01 px x/y); a view between two
    ticks rewinds it to that very pose (one rule: playback.between, on the same rounded rows), to the bit. The bandit
    walks a diagonal, so its x/y are never whole hundredths and its steps differ tick to tick."""
    room = routed(files, DIAGONAL, 552.0, 122.0)
    room.join()
    states = []
    for _ in range(12):
        room.step()
        states.append(room.snapshot())
    moving = 0
    for cursor in (6.0, 6.5, 7.25, 8.7, 9.5, 10.1, 11.9):
        playback = Playback(lambda s: None)
        latest = int(cursor) + 2 if int(cursor) + 2 <= 12 else 12
        for state in states[:latest]:
            playback.push(state, (state["tick"] - 1) / wire.HZ)
        shown = playback.enemies((latest - 1) / wire.HZ + (cursor - (latest - 2)) / wire.HZ)[BANDIT]
        assert abs(playback.cursor - cursor) < 1e-9
        body = room._rewound(playback.cursor)[BANDIT]
        assert (body.center_x, body.center_y, body.mesh_entity_data["elevation"], body.mesh_hd2d_floor) == shown, cursor
        lo, hi = pose(room, int(cursor)), pose(room, min(12, int(cursor) + 1))
        moving += cursor % 1 > 0 and lo[:2] != hi[:2]
    assert moving >= 3, "between two different poses, more than once"


def test_floors_are_asked_at_the_rewound_pose_on_stairs(files: dict[str, bytes]) -> None:
    """The bandit climbs the west stairs out of same_level's 1.5 m reach of a player on the ground beside them. A
    hitbox over both poses: with the view (it was in reach) a hit; now (out of reach) a miss. The level is the rewound
    pose's, against the attacker as it stands now."""
    room = routed(files, STAIRS, 328.0, 170.0)
    eid = room.join()
    found = None
    for _ in range(200):
        room.step()
        if room.tick > REWIND_CAP and pose(room, room.tick)[2] >= 49.0 and pose(room, room.tick - REWIND_CAP)[2] <= 47.0:
            found = room.tick - REWIND_CAP
            break
    assert found is not None, "climbing through 1.5 m (48 px)"
    then, now = shape(room, pose(room, found)), shape(room, pose_now(room))
    assert abs(then.x - now.x) < 1e-6 and abs(then.y - now.y) < room.hitbox, "one hitbox can cover both"
    stand(room, eid, (336.0, (then.y + now.y) / 2), facing=2)  # (on the ground east of the stairs, facing west)
    p = room.players[eid]
    assert room.stands(p.body) and p.body.center_x == 368.0
    assert hits(room, eid, found), "where the window showed it: in reach, a hit"
    assert not hits(room, eid, None), "now: 1.5 m or more above, out of reach"
    p.body.mesh_entity_data["elevation"] = 100.0  # (the attacker as it stands now decides its side: were it 3 m up)
    assert not hits(room, eid, found), "the level is asked of the attacker as it stands now"


def test_a_bridge_deck_over_the_attacker_is_never_in_reach_rewound_or_not(files: dict[str, bytes]) -> None:
    """The bandit walks the bridge deck (2 m up) over a player on the ground under it, through its hitbox in plan:
    never hit, with any view or none; a player on the deck at the same plan position hits it with that view."""
    room = routed(files, DECK, 472.0, 402.0, 64.0)
    under = room.join()
    deck = room.join()
    walking = []
    for _ in range(40):
        room.step()
        walking.append(room.tick)
    view = walking[-4]
    assert pose(room, view)[2:] == (64.0, "crossing/col_bridge_deck")
    box = edge(room, pose(room, view))
    stand(room, under, box, z=0.0)
    assert room.stands(room.players[under].body), "under the deck"
    stand(room, deck, box, z=64.0)
    assert room.stands(room.players[deck].body), "on the deck"
    assert hits(room, deck, view), "on the deck, as the window showed it: a hit"
    for v in (view, view + 0.5, room.tick - REWIND_CAP, None):
        assert not hits(room, under, v), f"{v}: under the deck, 2 m below: never"


def test_an_attacks_view_tick_travels_from_the_wire_to_the_hitbox(files: dict[str, bytes]) -> None:
    """An attack input carrying view_tick (wire v3, unchanged) is judged with it on the tick that reads it; the same
    input without one is judged now; the meant ``tick`` (the cooldown claim) never rewinds anything."""
    def trial(**view: Any) -> int:
        room = ground_room(files)
        eid = room.join()
        walking_east(room)
        target = room.tick - 3  # (4 ticks back on the tick that reads it)
        stand(room, eid, edge(room, pose(room, target)))
        room.input(eid, wire.input_frame(eid, 1, 0, 0, target, "attack", **{k: target for k in view}))
        room.step()
        assert room.players[eid].attack_seq == 1
        return room.enemies[BANDIT].hit_seq

    assert trial(view_tick=True) == 1, "judged at its view"
    assert trial() == 0, "no view: judged now (its old meant tick judges the cooldown only)"


def test_each_n7_instance_keeps_its_own_history_and_a_transfer_starts_anew(files: dict[str, bytes],
                                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    """N7: every instance is the room's own copy with its own history, of its own enemies only. A transfer joins the
    instance anew: a view from before it is judged now; an input naming the room left is dropped, view and all."""
    from mesh_net.world import WORLD_FILE, World

    files_ = {**with_entities(files, bandit(552.0, 122.0, route=GROUND)),
              WORLD_FILE: json.dumps({"id": "main", "start_scene": "start", "scenes": {"start": {"path": SCENE}}}).encode()}
    with disposable_project(files_, scaffold=False) as root:
        world = World(root)
    monkeypatch.setattr(world, "_cleanup", lambda: None)
    pid, _token = world.connect(None)
    party = world._create("start", 7)
    hub = world.hub
    ((_tick, start),) = party.room.history  # (copied with the room: its own enemies, never the prototype's)
    assert all(entry[0] is party.room.enemies[i] for i, entry in start.items())
    for _ in range(20):
        world.step()
    for inst, other in ((hub, party), (party, hub)):
        enemies = set(map(id, inst.room.enemies.values()))
        kept = {id(entry[0]) for _, poses in inst.room.history for entry in poses.values()}
        assert kept and kept <= enemies and not kept & set(map(id, other.room.enemies.values())), inst.id
    m = world.members[pid]
    assert world._move(m, hub, party, party.room.spawn)
    p = party.room.players[m.eid]
    assert p.joined == party.room.tick
    world.step()
    view = p.joined - 1
    world.input(pid, wire.input_frame(m.eid, 1, 0, 0, party.room.tick, "attack", view, room=party.id))
    world.step()
    assert p.attack_seq == 1 and party.room.unseen_views == 1, "a view from before the transfer: judged now"
    world.input(pid, wire.input_frame(m.eid, 2, 0, 0, hub.room.tick, "attack", hub.room.tick - 2, room=hub.id))
    assert not p.attacks and hub.room.unseen_views == 0 == hub.room.future_views, "the room left: dropped"


def test_rewind_is_off_switchable_and_checked() -> None:
    """mesh_net.server: --rewind on|off, else MESH_NET_REWIND (1/0), else on (REWIND); anything else is refused."""
    assert rewind_from(Namespace(rewind=None), {}) is True
    assert rewind_from(Namespace(rewind="off"), {"MESH_NET_REWIND": "1"}) is False
    assert rewind_from(Namespace(rewind="on"), {"MESH_NET_REWIND": "0"}) is True
    assert rewind_from(Namespace(rewind=None), {"MESH_NET_REWIND": "0"}) is False
    assert rewind_from(Namespace(rewind=None), {"MESH_NET_REWIND": "1"}) is True
    with pytest.raises(ValueError, match="MESH_NET_REWIND"):
        rewind_from(Namespace(rewind=None), {"MESH_NET_REWIND": "yes"})


def test_history_is_bounded_and_deterministic(files: dict[str, bytes]) -> None:
    """Two rooms from the same files, stepped alike, keep the same history (poses, ticks), never more than
    REWIND_CAP + 1 ticks of it, one entry per live enemy; a dead enemy's pose is not kept."""
    a, b = ground_room(files), ground_room(files)
    for _ in range(50):
        a.step()
        b.step()
    strip = [(t, {i: e[1:] for i, e in poses.items()}) for t, poses in a.history]
    assert strip == [(t, {i: e[1:] for i, e in poses.items()}) for t, poses in b.history]
    assert len(a.history) == REWIND_CAP + 1 and all(len(poses) == len(a.enemies) for _, poses in a.history)
    a.enemies[BANDIT].state = TargetState(hp=0.0, max_hp=1.0, dead=True)
    a.step()
    assert BANDIT not in a.history[-1][1]


def test_the_window_send_loop_carries_the_view_tick() -> None:
    """A window over a real server and socket (Arena.session's send loop, Client.input, wire.input_frame): an attack
    queued with its view tick reaches the authority with that view_tick, and only that input carries one."""
    import asyncio
    from types import SimpleNamespace

    from mesh_net.demo import Arena
    from mesh_net.scene_room import Feedback, Prediction, check_progress, check_state, parse_input
    from mesh_net.server import Server
    from tooling.m4_latency_probe import coop_room

    keys = SimpleNamespace(**{n: i for i, n in enumerate("W UP S DOWN A LEFT D RIGHT SPACE E ESCAPE F2 R N".split())})
    got: list[wire.Message] = []

    async def run() -> float:
        with coop_room() as room:
            server = Server(room)
            port = await server.start(0)
            shown: list[float] = []

            class Window(Arena):
                def on_state(self, state: wire.Message, entity: int, fresh: bool) -> None:
                    if fresh:
                        self.feedback.baseline(state, room.cooldown, self.clock())
                        shown.append(float(state["tick"]))
                        self.act("attack", state["tick"], shown[0])

                def describe(self, state: wire.Message, entity: int) -> str:
                    return ""

            window = Window(SimpleNamespace(push_handlers=lambda **_kw: None), SimpleNamespace(key=keys))
            window.prediction, window.feedback = Prediction(), Feedback()
            window.checks = {"check": lambda m: check_state(m, room.identity, room), "check_input": parse_input,
                             "progress": check_progress}
            received = room.input
            room.input = lambda e, m: (got.append(m), received(e, m))[1]  # type: ignore[method-assign]
            try:
                await asyncio.wait_for(window.session(port), 0.5)
            except TimeoutError:
                pass
            finally:
                await server.close()
            return shown[0]

    view = asyncio.run(run())
    carried = [m for m in got if "view_tick" in m]
    assert len(got) >= 3 and len(carried) == 1, got[:3]
    assert carried[0]["action"] == "attack" and carried[0]["view_tick"] == view
