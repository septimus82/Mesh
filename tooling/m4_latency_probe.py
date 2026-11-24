"""M4-0: today's online combat under simulated latency, measured headless (docs/plans/m4_online_combat.md).

    py -3.13 tooling/m4_latency_probe.py [--seeds N ...] [--sessions K] [--hz HZ] [--rto MS] [--json OUT]

The real authority (mesh_net.scene_room.SceneRoom, its step, input and _attack) and the client's real display rules
(mesh_net.scene_client.SceneArena.draw: the local avatar at the latest snapshot; everyone else through
mesh_net.playback.Playback, two ticks behind) run on one virtual millisecond clock. Between them, a seeded model of
the TCP link the server uses: a one-way delay with uniform jitter, and a lost segment arriving a retransmission later
(RTT + ``--rto``, Linux-like), everything behind it held up (in order, never dropped: TCP). The client sends its
intent every 1/HZ s on its own clock (mesh_net.demo.Arena.session), at a seeded phase to the server's tick that stays
fixed for the session. No socket, no window, no GPU, no wall clock: the same seeds give the same numbers. Several seeds
(``--seeds``) give each number's spread (``ranges``).

The window's combat presentation is the client's own rule (mesh_net.scene_room.Feedback, wire v3): a swing on the
first frame after the press, a hit flash on the first frame after a state whose enemy hit count rose.

What the tool adds that the game doesn't have: a scripted mover for the moving-target case (today's authority never
moves an enemy) and that enemy's position in the client's copy of each snapshot (today's wire carries none), shown
through Playback as a peer is. Hit questions are asked of the authority's own ``_attack`` (geometry and same_level),
with the bodies put where the client showed them, or where the authority had them on the tick the attack lands.
"""

from __future__ import annotations

import argparse
import copy
import heapq
import json
import math
import random
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):  # (run as a script: the checkout's packages; importing the module changes nothing)
    sys.path.insert(0, str(REPO))

from engine.combat_model import TargetState  # noqa: E402
from mesh_net import protocol as wire  # noqa: E402
from mesh_net.playback import Playback  # noqa: E402
from mesh_net.scene_room import COOP_SCENE, Body, Feedback, Player, SceneRoom, coop_files, disposable_project  # noqa: E402

FRAME_MS = 1000 / 60  # the client window's frame (mesh_net.demo.Arena.run)
RTO_MS = 200.0  # a lost segment arrives RTT + this later (Linux's RTO is SRTT + 4 RTTVAR, at least 200 ms; --rto)
# (round trip ms, one-way jitter +-ms, loss per message): the brief's 0/50/100/200 ms with a little jitter and loss
PROFILES = ((0, 0, 0.0), (0, 10, 0.01), (50, 10, 0.01), (100, 10, 0.01), (200, 10, 0.01))
BANDIT = "start_bandit_608_256_0_0"


def pct(values: list[float], q: float) -> float:
    """The ``q`` quantile (0..1), nearest rank: a sample that happened, never an interpolation (p50 too)."""
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))]


def summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"n": 0}
    return {"n": len(values), "p50": round(pct(values, 0.5), 1), "p95": round(pct(values, 0.95), 1),
            "max": round(max(values), 1)}


@dataclass
class Link:
    """One direction of a TCP connection: each message's arrival time (ms), in send order."""

    one_way_ms: float
    jitter_ms: float
    loss: float
    rng: random.Random
    last: float = -math.inf

    def arrival(self, sent: float) -> float:
        delay = max(0.0, self.one_way_ms + self.rng.uniform(-self.jitter_ms, self.jitter_ms))
        if self.rng.random() < self.loss:
            delay += 2 * self.one_way_ms + RTO_MS  # retransmitted after a timeout: RTT + RTO_MS
        self.last = max(self.last, sent + delay)  # head-of-line: never before the one sent earlier
        return self.last


@dataclass
class Session:
    """One client and the authority on one virtual clock. ``intent(now, shown)`` gives the held direction and an action
    from what the client shows (its own avatar's row); ``mover(tick)`` moves enemies before a tick (the tool's)."""

    room: SceneRoom
    rtt_ms: float
    jitter_ms: float
    loss: float
    seed: int
    intent: Callable[[float, list[Any]], tuple[int, int, str | None]] = lambda now, shown: (0, 0, None)
    mover: Callable[[int], None] | None = None
    setup: Callable[[SceneRoom, int], None] | None = None  # puts the joined player somewhere first (the tool's)
    frame: Callable[[float, "Session"], None] | None = None
    eid: int = 0
    now: float = 0.0
    latest: dict[str, Any] = field(default_factory=dict)
    playback: Playback = field(default_factory=lambda: Playback(lambda s: None))
    poses: dict[int, dict[str, Any]] = field(default_factory=dict)  # tick -> the authority's bodies after it
    applied: list[tuple[float, int]] = field(default_factory=list)  # (input send ms, tick it is applied on)
    # The most inputs read in one tick. (Reported only: since M4-1 a burst never ends a session; mesh_net.server's
    # InputBudget token bucket refuses only a sustained flood.)
    burst: int = 0

    def __post_init__(self) -> None:
        rng = random.Random(self.seed)
        self.up = Link(self.rtt_ms / 2, self.jitter_ms, self.loss, random.Random(rng.random()))
        self.down = Link(self.rtt_ms / 2, self.jitter_ms, self.loss, random.Random(rng.random()))
        self.period = 1000 / wire.HZ
        self.phase = rng.uniform(0, self.period)  # the client's send clock against the server's tick
        self.eid = self.room.join()
        if self.setup is not None:
            self.setup(self.room, self.eid)
        self.latest = self.observed()
        self.playback.push(self.latest, 0.0)
        self.to_server: list[tuple[float, int, float, dict[str, Any]]] = []  # (arrival, serial, sent, frame)
        self.to_client: list[tuple[float, int, dict[str, Any]]] = []
        self.seq = self.serial = 0
        self.next_send, self.next_tick, self.next_frame = self.phase, self.period, 0.0
        self.record()

    def observed(self) -> dict[str, Any]:
        """The snapshot, plus each enemy as a player row (id 1000+) for the client's Playback: the tool's addition."""
        state = self.room.snapshot()
        extra = [[1000 + i, round(e.body.center_x, 2), round(e.body.center_y, 2), 0, *self.room.level(e.body), 0, 0]
                 for i, (_, e) in enumerate(sorted(self.room.enemies.items()))]
        return {**state, "players": state["players"] + extra}

    def record(self) -> None:
        p = self.room.players[self.eid]
        z, floor = self.room.level(p.body)
        self.poses[self.room.tick] = {
            "own": (p.body.center_x, p.body.center_y, z, p.facing, floor),
            "enemies": {i: (e.body.center_x, e.body.center_y, e.body.mesh_entity_data.get("elevation", 0.0))
                        for i, e in self.room.enemies.items()},
            "hp": {i: e.state.hp for i, e in self.room.enemies.items()}}

    def own_row(self) -> list[Any]:
        return next(r for r in self.latest["players"] if r[0] == self.eid)

    def run(self, until_ms: float) -> None:
        while True:
            t = min(self.next_send, self.next_tick, self.next_frame,
                    self.to_server[0][0] if self.to_server else math.inf,
                    self.to_client[0][0] if self.to_client else math.inf)
            if t > until_ms:
                self.now = until_ms
                return
            self.now = t
            if self.to_server and self.to_server[0][0] <= t:
                _, _, sent, arrived = heapq.heappop(self.to_server)
                self.room.input(self.eid, arrived)
                self.applied.append((sent, self.room.tick + 1))  # (the next step reads it)
                self.burst = max(self.burst, sum(tick == self.room.tick + 1 for _, tick in self.applied[-9:]))
            elif self.next_tick <= t:
                if self.mover is not None:
                    self.mover(self.room.tick + 1)
                self.room.step()
                self.record()
                self.serial += 1
                heapq.heappush(self.to_client, (self.down.arrival(t), self.serial, self.observed()))
                self.next_tick += self.period
            elif self.to_client and self.to_client[0][0] <= t:
                _, _, state = heapq.heappop(self.to_client)
                if state["tick"] > self.latest["tick"]:
                    self.latest = state
                self.playback.push(state, t / 1000)
            elif self.next_send <= t:
                dx, dy, action = self.intent(t, self.own_row())
                self.seq += 1
                msg = wire.input_frame(self.eid, self.seq, dx, dy, self.latest["tick"] + 1, action)
                self.serial += 1
                heapq.heappush(self.to_server, (self.up.arrival(t), self.serial, t, msg))
                self.next_send += self.period
            else:
                if self.frame is not None:
                    self.frame(t, self)
                self.next_frame += FRAME_MS

    def landing_tick(self, press_ms: float) -> int | None:
        """The tick an action pressed at ``press_ms`` is applied on: it rides the next input sent."""
        return next((tick for sent, tick in self.applied if sent >= press_ms), None)

    def shown(self, t: float) -> dict[int, tuple[Any, ...]]:
        """What the window draws at ``t`` (SceneArena.draw): others through Playback, its own avatar at the latest."""
        positions = self.playback.positions(t / 1000)
        own = self.own_row()
        positions[self.eid] = (own[1], own[2], own[4], own[5])
        return positions


def ask(room: SceneRoom, own: tuple[Any, ...], targets: dict[str, tuple[float, float, float]]) -> tuple[bool, bool]:
    """(hit, every target in reach on the attacker's level): the authority's own ``_attack``, the attacker at ``own``
    (x, y, elevation, facing) and each enemy at ``targets``, all alive, then everything put back."""
    x, y, z, facing = own[:4]
    probe = Player(Body(x, y, *room.size, {**room.template, "elevation": z}), facing=facing)
    saved = {i: (e.state, e.dropped, e.body.center_x, e.body.center_y, e.body.mesh_entity_data, e.hit_seq)
             for i, e in room.enemies.items()}
    try:
        level = True
        for i, e in room.enemies.items():
            e.state = TargetState(hp=e.state.max_hp, max_hp=e.state.max_hp)
            e.body.center_x, e.body.center_y = targets[i][:2]
            e.body.mesh_entity_data = {**e.body.mesh_entity_data, "elevation": targets[i][2]}
            level = level and room._level(probe.body, e.body)
        room._attack(probe)
        return any(e.state.hp < e.state.max_hp for e in room.enemies.values()), level
    finally:
        for i, e in room.enemies.items():
            e.state, e.dropped, e.body.center_x, e.body.center_y, e.body.mesh_entity_data, e.hit_seq = saved[i]


# --- rooms -----------------------------------------------------------------------------------------------------------

@contextmanager
def coop_room() -> Iterator[SceneRoom]:
    """The packaged co-op room (2D), its gate opened so the bandit can be reached."""
    with disposable_project(coop_files(), scaffold=False) as root:
        room = SceneRoom(root / COOP_SCENE, root)
    room.locked.clear()
    yield room


@contextmanager
def stairs_room() -> Iterator[SceneRoom]:
    """The floors demo's crossing (HD-2D: tooling/hd2d_floors_demo.py) with the co-op bandit on the ground right beside
    the west stairs' east edge, level with the stairs where they are 1.5 m up (BODY: same_level's reach)."""
    sys.path.insert(0, str(REPO / "tooling"))
    try:
        import hd2d_floors_demo
    finally:
        sys.path.remove(str(REPO / "tooling"))
    bandit = next(e for e in json.loads(files("mesh_net").joinpath("coop", "scene.json").read_text(encoding="utf-8"))
                  ["entities"] if e["id"] == BANDIT)
    scene_rel = "packs/core_regions/scenes/start.json"
    with disposable_project({}, scaffold=False) as root:  # (the build writes nowhere else)
        project = hd2d_floors_demo.build(root / "crossing")
        crossing = {q.relative_to(project).as_posix(): q.read_bytes() for q in project.rglob("*") if q.is_file()}
    scene = json.loads(crossing[scene_rel])
    scene["entities"].append({**copy.deepcopy(bandit), "x": 384.0, "y": 275.0})
    with disposable_project({**crossing, scene_rel: json.dumps(scene).encode()}, scaffold=False) as root:
        room = SceneRoom(root / scene_rel, root)  # (as tests/test_mesh_net_hd2d.py builds the crossing's room)
    yield room


def place(room: SceneRoom, eid: int, x: float, y: float, facing: int) -> None:
    body = room.players[eid].body
    body.center_x, body.center_y = x, y
    room.players[eid].facing = facing


# --- measurements ----------------------------------------------------------------------------------------------------

def movement(rtt: float, jitter: float, loss: float, seed: int, trials: int = 40) -> dict[str, Any]:
    """Press a direction, hold 400 ms, release, rest: when does the local avatar move and stop on screen, and when does
    a peer (same link statistics) see it move. Plus the local avatar's frame-to-frame steps while it walks."""
    rng = random.Random(seed)
    presses = []  # (press ms, release ms, dx)
    t = 1000.0
    for i in range(trials):
        start = t + rng.uniform(0, 100)
        presses.append((start, start + 400, 1 if i % 2 == 0 else -1))
        t = start + 1400
    trace: list[tuple[float, float, float]] = []  # (frame ms, own x shown, own x as a peer shows it)

    def intent(now: float, shown: list[Any]) -> tuple[int, int, None]:
        held = next((dx for a, b, dx in presses if a <= now < b), 0)
        return held, 0, None

    def frame(now: float, s: Session) -> None:
        trace.append((now, s.own_row()[1], s.playback.positions(now / 1000)[s.eid][0]))

    with coop_room() as room:
        s = Session(room, rtt, jitter, loss, seed, intent=intent, frame=frame)
        s.run(t + 500)
    start_local: list[float] = []
    start_peer: list[float] = []
    stop_local: list[float] = []
    frozen: list[float] = []
    steps: list[float] = []
    for a, b, _ in presses:
        before = [r for r in trace if r[0] <= a][-1]
        moved = next((r for r in trace if r[0] > a and r[1] != before[1]), None)
        peer = next((r for r in trace if r[0] > a and abs(r[2] - before[2]) > 1e-6), None)
        last_change = max((r[0] for i, r in enumerate(trace[1:], 1) if a < r[0] < b + 1000 and r[1] != trace[i - 1][1]),
                          default=None)
        if moved:
            start_local.append(moved[0] - a)
        if peer:
            start_peer.append(peer[0] - a)
        if last_change:
            stop_local.append(max(0.0, last_change - b))
        walk = [r[1] for r in trace if (moved[0] if moved else b) <= r[0] < b]
        deltas = [abs(q - p) for p, q in zip(walk, walk[1:])]
        frozen.extend(1.0 if d == 0 else 0.0 for d in deltas)
        steps.extend(deltas)
    return {"local_first_move_ms": start_local, "peer_first_move_ms": start_peer, "local_stop_after_release_ms": stop_local,
            "frozen": frozen, "steps": steps, "max_inputs_in_one_tick": s.burst}


def attack(rtt: float, jitter: float, loss: float, seed: int, trials: int = 30) -> dict[str, Any]:
    """Stand next to the bandit, press attack: when does the hit show (the snapshot's lower HP: the caption, or the
    sprite hidden at 0), and when do the swing and the confirmed hit's flash show (Feedback)? The bandit's HP is put
    back between trials (the tool's)."""
    rng = random.Random(seed)
    presses = [1000.0 + i * 1500 + rng.uniform(0, 100) for i in range(trials)]
    sent: set[float] = set()
    hp_seen: list[tuple[float, float]] = []
    feedback = Feedback()
    shown: list[Any] = [None]  # (the state the last frame showed)
    swings: list[float] = []  # (the frame each press swung on: inf when the cooldown refused it)
    flashes: list[float] = []

    def intent(now: float, shown: list[Any]) -> tuple[int, int, str | None]:
        due = [p for p in presses if p <= now and p not in sent]
        sent.update(due)
        return 0, 0, "attack" if due else None

    def frame(now: float, s: Session) -> None:
        hp_seen.append((now, next(r[1] for r in s.latest["enemies"] if r[0] == BANDIT)))
        if shown[0] is None:
            feedback.baseline(s.latest, room.cooldown)
        elif s.latest is not shown[0]:
            flashes.extend(now for _ in feedback.update(s.latest, s.eid)[1])
        shown[0] = s.latest
        if len(swings) < len(presses) and presses[len(swings)] <= now:  # (a press: the window's next frame reads it)
            swings.append(now if feedback.press(now / 1000) else math.inf)

    with coop_room() as room:
        s = Session(room, rtt, jitter, loss, seed, intent=intent, frame=frame,
                    setup=lambda room, eid: place(room, eid, 568.0, 256.0, 0))
        for p in presses:
            s.run(p + 1200)
            room.enemies[BANDIT].state = TargetState(hp=3.0, max_hp=3.0)
    confirm = []
    for p in presses:
        seen = next((t for (_, before), (t, hp) in zip(hp_seen, hp_seen[1:]) if t > p and hp < before), None)
        if seen is not None:
            confirm.append(seen - p)
    swing = [t - p for p, t in zip(presses, swings) if t < math.inf]
    flash = [next((t for t in flashes if t > p), math.inf) - p for p in presses]
    return {"hit_confirmed_ms": confirm, "swing_visible_ms": swing, "hit_flash_ms": [f for f in flash if f < 1200],
            "trials": trials}


def judge(s: Session, samples: list[tuple[float, tuple[Any, ...], dict[str, tuple[float, float, float]]]],
          ) -> dict[str, Any]:
    """Per sampled frame (a press there): the hit as the attacker's screen showed it against the authority's hit on the
    tick the press lands; also with the authority rewinding the targets to what the screen showed (lag compensation)."""
    counts = {"view_hit": 0, "view_miss": 0, "looked_hit_missed": 0, "looked_miss_hit": 0, "rewind_disagree": 0,
              "level_looked_ok_refused": 0, "level_looked_refused_ok": 0}
    for t, own, targets in samples:
        tick = s.landing_tick(t)
        if tick is None or tick not in s.poses:
            continue
        server = s.poses[tick]
        seen_hit, seen_level = ask(s.room, own, targets)
        real_hit, real_level = ask(s.room, server["own"], server["enemies"])
        rewound_hit, _ = ask(s.room, server["own"], targets)
        counts["view_hit" if seen_hit else "view_miss"] += 1
        counts["looked_hit_missed"] += seen_hit and not real_hit
        counts["looked_miss_hit"] += real_hit and not seen_hit
        counts["rewind_disagree"] += rewound_hit != seen_hit
        counts["level_looked_ok_refused"] += seen_hit and not real_hit and seen_level and not real_level
        counts["level_looked_refused_ok"] += real_hit and not seen_hit and real_level and not seen_level
    return counts


def moving_target(rtt: float, jitter: float, loss: float, seed: int, speed: float, ms: float = 12000) -> dict[str, Any]:
    """A still attacker facing a bandit the tool walks back and forth through its hitbox at ``speed`` px/s, shown on
    the attacker's screen through Playback as a peer is. Fairness, and how the target's motion looks."""
    lo, hi = 530.0, 640.0
    span = 2 * (hi - lo)

    def at(tick: int) -> float:
        d = (tick * speed / wire.HZ) % span
        return lo + (d if d <= hi - lo else span - d)

    samples: list[tuple[float, tuple[Any, ...], dict[str, tuple[float, float, float]]]] = []
    shown_x: list[float] = []

    with coop_room() as room:
        def mover(tick: int) -> None:
            room.enemies[BANDIT].body.center_x = at(tick)

        def frame(now: float, s: Session) -> None:
            if now < 1000:
                return
            shown = s.shown(now)
            own = shown[s.eid]
            bx, by, bz, _floor = shown[1000]
            samples.append((now, (own[0], own[1], own[2], 0), {BANDIT: (bx, by, bz)}))
            shown_x.append(bx)

        s = Session(room, rtt, jitter, loss, seed, mover=mover, frame=frame,
                    setup=lambda room, eid: place(room, eid, 520.0, 256.0, 0))
        s.run(ms)
        result = judge(s, samples)
    deltas = [q - p for p, q in zip(shown_x, shown_x[1:])]
    per_frame = speed / 60
    turns = round((ms - 1000) / 1000 * speed / (hi - lo))  # the target's own reversals in the sampled time
    signs = [d > 0 for d in deltas if abs(d) > 1e-6]
    reversals = sum(a != b for a, b in zip(signs, signs[1:]))
    longest = run = 0
    for d in deltas:
        run = run + 1 if abs(d) <= 1e-6 else 0
        longest = max(longest, run)
    return {**result, "target_frames": len(deltas), "target_frozen": sum(abs(d) <= 1e-6 for d in deltas),
            "max_target_freeze_frames": longest, "target_snaps_over_2x_speed": sum(abs(d) > 2 * per_frame + 0.01 for d in deltas),
            "target_extra_reversals": max(0, reversals - turns)}


def moving_attacker(rtt: float, jitter: float, loss: float, seed: int, ms: float = 12000) -> dict[str, Any]:
    """Today's real case: the attacker walks up to the (still) bandit and away again, its screen showing itself at the
    latest snapshot. Fairness only (the target never moves)."""
    samples: list[tuple[float, tuple[Any, ...], dict[str, tuple[float, float, float]]]] = []

    def intent(now: float, shown: list[Any]) -> tuple[int, int, None]:
        return (1 if (now // 700) % 2 == 0 else -1), 0, None

    with coop_room() as room:
        bandit = room.enemies[BANDIT].body
        target = {BANDIT: (bandit.center_x, bandit.center_y, 0.0)}

        def frame(now: float, s: Session) -> None:
            if now >= 1000:
                row = s.own_row()
                samples.append((now, (row[1], row[2], row[4], row[3]), target))

        s = Session(room, rtt, jitter, loss, seed, intent=intent, frame=frame,
                    setup=lambda room, eid: place(room, eid, 500.0, 256.0, 0))
        s.run(ms)
        return judge(s, samples)


def to_stairs_edge(room: SceneRoom, eid: int) -> None:
    """Walk (no link: straight into the authority) from the spawn onto the west stairs and east to their edge."""
    p, seq = room.players[eid], 0
    for dx, dy, done in ((-1, 0, lambda b: b.center_x <= 317.0), (0, 1, lambda b: b.center_y >= 204.0),
                         (1, 0, lambda b: b.center_x >= 350.0)):
        for _ in range(100):
            if done(p.body):
                break
            seq += 1
            room.input(eid, wire.input_frame(eid, seq, dx, dy, room.tick + 1))
            room.step()
    p.seq = 0  # (the session's own inputs count from 1)
    assert p.body.mesh_hd2d_floor == "crossing/col_stairs_west" and p.body.center_x >= 350.0, "not at the stairs' edge"


def stairs(rtt: float, jitter: float, loss: float, seed: int, ms: float = 16000) -> dict[str, Any]:
    """HD-2D: the attacker strafes up and down the west stairs against their east edge, facing east, at a bandit on the
    ground beside them: in reach in the plane from about 1.15 m to 1.8 m up the stairs, and same_level refuses from
    1.5 m (BODY). The tool turns it by the authority's position, so every latency walks the same stretch; what is
    judged is the screen (its latest snapshot). Fairness, by cause."""
    with stairs_room() as room:
        bandit = room.enemies[BANDIT].body
        target = {BANDIT: (bandit.center_x, bandit.center_y, 0.0)}
        samples: list[tuple[float, tuple[Any, ...], dict[str, tuple[float, float, float]]]] = []
        heading = {"dy": 1}

        def intent(now: float, shown: list[Any]) -> tuple[int, int, None]:
            y = room.players[s.eid].body.center_y
            heading["dy"] = -1 if y >= 268.0 else 1 if y <= 225.0 else heading["dy"]
            return 1, heading["dy"], None

        def frame(now: float, s: Session) -> None:
            if now >= 1000:
                row = s.own_row()
                samples.append((now, (row[1], row[2], row[4], row[3]), target))

        s = Session(room, rtt, jitter, loss, seed, intent=intent, frame=frame, setup=to_stairs_edge)
        s.run(ms)
        result = judge(s, samples)
        floors = {pose["own"][4] for pose in s.poses.values()}
        heights = [pose["own"][2] for pose in s.poses.values()]
    return {**result, "floors_walked": sorted(f for f in floors if f), "max_elevation_px": max(heights)}


def pooled(scenario: Callable[..., dict[str, Any]], seeds: list[int], *args: Any) -> dict[str, Any]:
    """One scenario over several sessions: lists joined, counts added, ``max_`` the most. Each session keeps one fixed
    phase between the client's send clock and the server's tick, and one phase alone skews every delay; real clients
    drift instead (their loops sleep 1/HZ after each send, so the phase wanders), which pooling many fixed phases stands
    in for *(an approximation: a drifting phase is not modelled)*."""
    total: dict[str, Any] = {}
    for seed in seeds:
        for key, value in scenario(*args[:3], seed, *args[3:]).items():
            if key not in total:
                total[key] = value
            elif key.startswith("max_"):
                total[key] = max(total[key], value)
            else:
                total[key] = total[key] + value
    return total


def fairness(c: dict[str, Any]) -> dict[str, Any]:
    n = c["view_hit"] + c["view_miss"]
    result = {"samples": n,
              "looked_hit_but_missed_pct": round(100 * c["looked_hit_missed"] / max(1, c["view_hit"]), 1),
              "looked_miss_but_hit_pct": round(100 * c["looked_miss_hit"] / max(1, c["view_miss"]), 1),
              "disagree_pct": round(100 * (c["looked_hit_missed"] + c["looked_miss_hit"]) / max(1, n), 1),
              "disagree_with_rewind_pct": round(100 * c["rewind_disagree"] / max(1, n), 1),
              "level_caused_disagree_pct": round(100 * (c["level_looked_ok_refused"] + c["level_looked_refused_ok"])
                                                 / max(1, n), 1)}
    if "target_frames" in c:
        result.update({"target_frames_frozen_pct": round(100 * c["target_frozen"] / max(1, c["target_frames"]), 1),
                       "target_longest_freeze_ms": round(c["max_target_freeze_frames"] * FRAME_MS),
                       "target_snaps_over_2x_speed": c["target_snaps_over_2x_speed"],
                       "target_extra_reversals": c["target_extra_reversals"]})
    if "floors_walked" in c:
        result.update({"floors_walked": sorted(set(c["floors_walked"])), "max_elevation_px": c["max_elevation_px"]})
    return result


def measure(seed: int = 7, sessions: int = 6) -> dict[str, Any]:
    rows = []
    for i, profile in enumerate(PROFILES):
        seeds = [seed * 1000 + i * 100 + k for k in range(sessions)]
        m = pooled(movement, seeds, *profile)
        a = pooled(attack, seeds, *profile)
        rows.append({
            "rtt_ms": profile[0], "jitter_ms": profile[1], "loss": profile[2], "hz": wire.HZ,
            "movement": {"local_first_move_ms": summary(m["local_first_move_ms"]),
                         "peer_first_move_ms": summary(m["peer_first_move_ms"]),
                         "local_stop_after_release_ms": summary(m["local_stop_after_release_ms"]),
                         "local_frames_without_movement_while_walking": round(sum(m["frozen"]) / max(1, len(m["frozen"])), 3),
                         "local_largest_frame_step_px": round(max(m["steps"], default=0.0), 1),
                         "most_inputs_in_one_tick": m["max_inputs_in_one_tick"]},
            "attack": {"swing_visible_ms": summary(a["swing_visible_ms"]), "hit_confirmed_ms": summary(a["hit_confirmed_ms"]),
                       "hit_flash_ms": summary(a["hit_flash_ms"]), "hits_seen": f"{len(a['hit_confirmed_ms'])}/{a['trials']}"},
            "moving_target_70": fairness(pooled(moving_target, seeds, *profile, 70.0)),
            "moving_target_150": fairness(pooled(moving_target, seeds, *profile, 150.0)),
            "moving_attacker": fairness(pooled(moving_attacker, seeds, *profile)),
            "stairs": fairness(pooled(stairs, seeds, *profile))})
    return {"seed": seed, "sessions_per_profile": sessions, "frame_ms": round(FRAME_MS, 2), "rto_ms": RTO_MS,
            "hz": wire.HZ, "profiles": rows}


def snapshot_bytes() -> dict[str, dict[int, int]]:
    """Encoded snapshot size (bytes, with its LF) by player count, in both rooms."""
    sizes: dict[str, dict[int, int]] = {}
    for name, opened in (("coop_2d", coop_room), ("crossing_hd2d", stairs_room)):
        with opened() as room:
            sizes[name] = {}
            for n in range(1, wire.MAX_PLAYERS + 1):
                room.join()
                if n in (1, 2, 8):
                    sizes[name][n] = len(wire.encode(room.snapshot()))
    return sizes


def ranges(runs: list[Any]) -> Any:
    """Several seeds' results as one: every number becomes [lowest, highest]; anything else is the first run's."""
    first = runs[0]
    if isinstance(first, dict):
        return {k: ranges([r[k] for r in runs]) for k in first}
    if isinstance(first, list) and all(isinstance(r, list) and len(r) == len(first) for r in runs):
        return [ranges([r[i] for r in runs]) for i in range(len(first))]
    if isinstance(first, (int, float)) and not isinstance(first, bool) and all(isinstance(r, (int, float)) for r in runs):
        low, high = min(runs), max(runs)
        return first if low == high else [low, high]
    return first


def main() -> None:
    global RTO_MS
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seeds", type=int, nargs="+", default=[7, 8, 9], help="one run per seed; the spread is "
                                                                                 "reported as [lowest, highest]")
    parser.add_argument("--sessions", type=int, default=24, help="sessions pooled per latency profile")
    parser.add_argument("--rto", type=float, default=RTO_MS, help="a lost segment arrives RTT + this many ms later")
    parser.add_argument("--hz", type=int, default=wire.HZ, help="what-if: the authority's tick and the client's send "
                                                                "rate (the game's is mesh_net.protocol.HZ)")
    parser.add_argument("--json", help="also write the full result here")
    args = parser.parse_args()
    RTO_MS = args.rto
    with mock.patch.object(wire, "HZ", args.hz):
        runs = [measure(seed, args.sessions) for seed in args.seeds]
        result = {"seeds": args.seeds, "range": ranges(runs), "runs": runs, "snapshot_bytes": snapshot_bytes()}
    text = json.dumps(result, indent=1)
    if args.json:
        Path(args.json).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
