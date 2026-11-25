"""M4-0: today's online combat under simulated latency, measured headless (docs/plans/m4_online_combat.md).

    py -3.13 tooling/m4_latency_probe.py [--seeds N ...] [--sessions K] [--hz HZ] [--rto MS] [--depth D] [--json OUT]

The real authority (mesh_net.scene_room.SceneRoom, its step, input queue and _attack) and the client's real display
rules (mesh_net.scene_client.SceneArena: since M4-3 the local avatar as mesh_net.scene_room.Prediction shows it, built
at a direction press, walked at each send, reconciled at each snapshot; everyone else through
mesh_net.playback.Playback, two ticks behind) run on one virtual millisecond clock. Between them, a seeded model of
the TCP link the server uses: a one-way delay with uniform jitter, and a lost segment arriving a retransmission later
(RTT + ``--rto``, Linux-like), everything behind it held up (in order, never dropped: TCP). The client sends its
intent every 1/HZ s on its own clock (mesh_net.demo.Arena.session), at a seeded phase to the server's tick that stays
fixed for the session. No socket, no window, no GPU, no wall clock: the same seeds give the same numbers. Several seeds
(``--seeds``) give each number's spread (``ranges``).

The window's combat presentation is the client's own rule (mesh_net.scene_room.Feedback, wire v3): a swing on the
first frame after the press, a hit flash on the first frame after a state whose enemy hit count rose. Every input
carries the tick Feedback reckons (one estimate, as the arenas send). ``--depth``: what-if, the server's input queue
(mesh_net.scene_room.DEPTH, owner decision OD11), with ``--hold`` and ``--drain``. ``walking`` (M4-3 round 2) measures the queue's costs while a player
never stops: how deep it stays, how late a peer sees the walk, how long a swing made while walking waits.

Moving targets (M4-4) are the real mover: the bandit walks a FloorRoute on the authority (engine.hd2d.route, the model
single-player's behaviour runs), its rows carry where it is, and the window shows it through Playback.enemies, two
ticks behind, as it shows peers (never predicted). Hit questions are asked of the authority's own ``_attack``
(geometry and same_level; its first update), with the bodies put where the client showed them, or where the authority
had them on the tick the attack lands; a disagreement is put down to the floor rule, the target's motion or the
attacker's (``judge``).
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
from functools import cache
from importlib.resources import files
from pathlib import Path
from typing import Any
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):  # (run as a script: the checkout's packages; importing the module changes nothing)
    sys.path.insert(0, str(REPO))

from engine.combat_model import TargetState  # noqa: E402
from mesh_net import protocol as wire  # noqa: E402
from mesh_net import scene_room  # noqa: E402
from mesh_net.playback import Playback  # noqa: E402
from mesh_net.scene_room import (  # noqa: E402
    COOP_SCENE,
    Body,
    Feedback,
    Player,
    Prediction,
    SceneRoom,
    coop_files,
    disposable_project,
    facing_of,
)

FRAME_MS = 1000 / 60  # the client window's frame (mesh_net.demo.Arena.run)
RTO_MS = 200.0  # a lost segment arrives RTT + this later (Linux's RTO is SRTT + 4 RTTVAR, at least 200 ms; --rto)
# (round trip ms, one-way jitter +-ms, loss per message): the brief's 0/50/100/200 ms with a little jitter and loss
PROFILES = ((0, 0, 0.0), (0, 10, 0.01), (50, 10, 0.01), (100, 10, 0.01), (200, 10, 0.01))
JITTER_ONLY = (100, 10, 0.0)  # (M4-3: corrections from jitter alone, reported beside the profiles)
BANDIT = "start_bandit_608_256_0_0"
CORRECTED = 0.05  # px: a reconciliation that moves the avatar further than this is a correction (the wire rounds x/y
# to 0.01 px, so replays from a snapshot differ by up to about 0.014 px from the last prediction: never one)


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
    # (dx, dy, action[, the tick the action is meant for: the window's Feedback.press; else the tick it reckons now])
    intent: Callable[[float, list[Any]], tuple[Any, ...]] = lambda now, shown: (0, 0, None)
    mover: Callable[[int], None] | None = None
    setup: Callable[[SceneRoom, int], None] | None = None  # puts the joined player somewhere first (the tool's)
    frame: Callable[[float, "Session"], None] | None = None
    held: Callable[[float], tuple[int, int]] | None = None  # the direction held at a time: a change to one is a press
    eid: int = 0
    now: float = 0.0
    latest: dict[str, Any] = field(default_factory=dict)
    playback: Playback = field(default_factory=lambda: Playback(lambda s: None))
    poses: dict[int, dict[str, Any]] = field(default_factory=dict)  # tick -> the authority's bodies after it
    applied: list[tuple[float, int]] = field(default_factory=list)  # (input send ms, tick it is applied on)
    # The most inputs arriving for one tick. (Reported only: since M4-1 a burst never ends a session; mesh_net.server's
    # InputBudget token bucket refuses only a sustained flood. Since M4-3 the server reads one a tick: DEPTH.)
    burst: int = 0
    prediction: Prediction = field(default_factory=Prediction)  # the window's own avatar (SceneArena)
    feedback: Feedback = field(default_factory=Feedback)  # its reckoning of the room's tick (every input carries it)
    corrections: list[tuple[float, float, float, bool]] = field(default_factory=list)  # (ms, x/y px, z px, floor?)
    sends: list[tuple[float, int]] = field(default_factory=list)  # (ms, seq) of each input sent
    acks: dict[int, int] = field(default_factory=dict)  # tick -> the seq the authority had read after it
    held_steps: int = 0  # ticks the authority walked a direction no input of that tick gave (its queue empty: HOLD)
    own_shown: tuple[Any, ...] = ()  # (x, y, elevation, floor) of the own avatar on the last frame
    hits: list[float] = field(default_factory=list)  # ms each confirmed hit arrived (Feedback.update)
    # The window's own key and action handling (mesh_net.demo.Arena: press, act, outgoing), driving the keys ``held``
    # says; else ``intent`` gives each input (the older scenarios).
    arena: Any = None
    waiting: list[int] = field(default_factory=list)  # inputs waiting in the authority's queue after each tick

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
        self.feedback.baseline(self.latest, self.room.cooldown, 0.0)
        self.prediction.start(self.room, self.latest, self.eid)
        self.own_shown = self.prediction.shown(0.0)
        self.pressed = (0, 0)
        if self.arena is not None:
            self.arena.prediction, self.arena.feedback = self.prediction, self.feedback
            self.arena.clock = lambda: self.now / 1000
        self.to_server: list[tuple[float, int, float, dict[str, Any]]] = []  # (arrival, serial, sent, frame)
        self.to_client: list[tuple[float, int, dict[str, Any]]] = []
        self.seq = self.serial = 0
        self.next_send, self.next_tick, self.next_frame = self.phase, self.period, 0.0
        self.record()

    def observed(self) -> dict[str, Any]:
        """The snapshot the client gets (wire v3: enemy rows carry where each enemy is)."""
        return self.room.snapshot()

    def record(self) -> None:
        p = self.room.players[self.eid]
        self.acks[self.room.tick] = p.ack
        z, floor = self.room.level(p.body)
        self.poses[self.room.tick] = {
            "own": (p.body.center_x, p.body.center_y, z, p.facing, floor),
            "enemies": {i: (e.body.center_x, e.body.center_y, e.body.mesh_entity_data.get("elevation", 0.0))
                        for i, e in self.room.enemies.items()},
            "hp": {i: e.state.hp for i, e in self.room.enemies.items()},
            "hit_seq": {i: e.hit_seq for i, e in self.room.enemies.items()},
            "enemy_floors": {i: e.body.mesh_hd2d_floor for i, e in self.room.enemies.items()}}

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
                p = self.room.players[self.eid]
                self.held_steps += 0 < p.held < self.room.hold and bool(p.dx or p.dy)
                self.waiting.append(len(p.moves))
                self.record()
                self.serial += 1
                heapq.heappush(self.to_client, (self.down.arrival(t), self.serial, self.observed()))
                self.next_tick += self.period
            elif self.to_client and self.to_client[0][0] <= t:
                _, _, state = heapq.heappop(self.to_client)
                if state["tick"] > self.latest["tick"]:  # (SceneArena.on_state: reconciled, then the reckoning)
                    self.latest = state
                    self.corrections.append((t, *self.prediction.reconcile(state, self.eid)))
                    self.hits.extend(t for _ in self.feedback.update(state, self.eid, t / 1000)[1])
                self.playback.push(state, t / 1000)
            elif self.next_send <= t:
                if self.arena is not None:  # (Arena.session's send loop)
                    (dx, dy), action, tick = self.arena.outgoing()
                else:
                    dx, dy, action, *meant = self.intent(t, self.own_row())
                    dx, dy = self.prediction.next((dx, dy))  # (Arena.outgoing: the input a press built, if any)
                    tick = meant[0] if meant and meant[0] is not None else self.feedback.tick(t / 1000)
                self.seq += 1
                self.prediction.sent(self.seq)
                self.sends.append((t, self.seq))
                msg = wire.input_frame(self.eid, self.seq, dx, dy, tick, action)
                self.serial += 1
                heapq.heappush(self.to_server, (self.up.arrival(t), self.serial, t, msg))
                self.next_send += self.period
            else:
                if self.held is not None:  # (Arena.press: the frame's dispatch_events reads a direction pressed)
                    direction = self.held(t)
                    if self.arena is not None and direction != self.pressed:
                        keys = {d: k for k, d in self.arena.directions.items()}
                        if self.pressed != (0, 0):
                            self.arena.release(keys[self.pressed], 0)
                        if direction != (0, 0):
                            self.arena.press(keys[direction], 0)
                    elif direction != self.pressed and direction != (0, 0):
                        self.prediction.press(direction)
                    self.pressed = direction
                self.own_shown = self.prediction.shown(FRAME_MS / 1000)  # (SceneArena.draw)
                if self.frame is not None:
                    self.frame(t, self)
                self.next_frame += FRAME_MS

    def landing_tick(self, press_ms: float) -> int | None:
        """The tick an action pressed at ``press_ms`` runs on: it rides the next input sent, and runs on the tick that
        reads that input or a later one (mesh_net.scene_room.SceneRoom.step: the first whose ``ack`` reaches it)."""
        seq = next((seq for sent, seq in self.sends if sent >= press_ms), None)
        return next((tick for tick, ack in sorted(self.acks.items()) if seq is not None and ack >= seq), None)

    def combat_pose(self, tick: int) -> tuple[Any, ...]:
        """(x, y, elevation, facing) the authority's actions on ``tick`` ran from: where the player stood before that
        tick's step, facing as the input it read turned it (SceneRoom.step)."""
        before, after = self.poses[tick - 1]["own"], self.poses[tick]["own"]
        return before[0], before[1], before[2], after[3]

    def shown(self, t: float) -> dict[int, tuple[Any, ...]]:
        """What the window draws at ``t`` (SceneArena.draw): others through Playback, its own avatar as predicted."""
        positions = self.playback.positions(t / 1000)
        positions[self.eid] = self.own_shown
        return positions

    def enemies_shown(self, t: float) -> dict[str, tuple[float, float, float]]:
        """Each enemy (x, y, elevation px) as the window draws it at ``t``: Playback, two ticks behind (M4-4)."""
        return {i: at[:3] for i, at in self.playback.enemies(t / 1000).items()}


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


@cache
def crossing_files() -> dict[str, bytes]:
    """The floors demo's crossing project (HD-2D: tooling/hd2d_floors_demo.py), built once."""
    sys.path.insert(0, str(REPO / "tooling"))
    try:
        import hd2d_floors_demo
    finally:
        sys.path.remove(str(REPO / "tooling"))
    with disposable_project({}, scaffold=False) as root:  # (the build writes nowhere else)
        project = hd2d_floors_demo.build(root / "crossing")
        return {q.relative_to(project).as_posix(): q.read_bytes() for q in project.rglob("*") if q.is_file()}


@contextmanager
def stairs_room(x: float = 384.0, y: float = 275.0, route: dict[str, Any] | None = None) -> Iterator[SceneRoom]:
    """The crossing with the co-op bandit at (x, y): by default on the ground right beside the west stairs' east edge,
    level with the stairs where they are 1.5 m up (BODY: same_level's reach). ``route``: its FloorRoute settings, which
    the authority walks it by (M4-4)."""
    bandit = copy.deepcopy(next(e for e in json.loads(files("mesh_net").joinpath("coop", "scene.json").read_text(
        encoding="utf-8"))["entities"] if e["id"] == BANDIT))
    if route is not None:
        bandit["behaviours"] = [*bandit["behaviours"], "FloorRoute"]
        bandit.setdefault("behaviour_config", {})["FloorRoute"] = route
    scene_rel = "packs/core_regions/scenes/start.json"
    crossing = crossing_files()
    scene = json.loads(crossing[scene_rel])
    scene["entities"].append({**bandit, "x": x, "y": y})
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

    def held(now: float) -> tuple[int, int]:
        return next((dx for a, b, dx in presses if a <= now < b), 0), 0

    def intent(now: float, shown: list[Any]) -> tuple[int, int, None]:
        return *held(now), None

    def frame(now: float, s: Session) -> None:
        trace.append((now, s.own_shown[0], s.playback.positions(now / 1000)[s.eid][0]))

    with coop_room() as room:
        s = Session(room, rtt, jitter, loss, seed, intent=intent, frame=frame, held=held)
        s.run(t + 500)
        step = room.step_px
    start_local: list[float] = []
    start_peer: list[float] = []
    stop_local: list[float] = []
    frozen: list[float] = []
    steps: list[float] = []
    for a, b, dx in presses:
        before = [r for r in trace if r[0] <= a][-1]
        # (half a step the way pressed: a correction's fading offset never counts as the press's move)
        moved = next((r for r in trace if r[0] > a and (r[1] - before[1]) * dx >= step / 2), None)
        peer = next((r for r in trace if r[0] > a and abs(r[2] - before[2]) > 1e-6), None)
        last_change = max((r[0] for i, r in enumerate(trace[1:], 1)
                           if a < r[0] < b + 1000 and abs(r[1] - trace[i - 1][1]) > 0.01), default=None)
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
            "frozen": frozen, "steps": steps, "max_inputs_in_one_tick": s.burst, **queue(s)}


def queue(s: Session) -> dict[str, Any]:
    """The prediction's corrections and what the authority's input queue did (M4-3): every reconciliation's x/y move
    (px) and whether it changed elevation (by over CORRECTED px) or floor; directions dropped from a full queue; steps
    walked on an empty one. Also, from 1 s on, the large ones (over one step: ``large``, over 30 px, with an elevation
    or floor snap) and the minutes they are counted over; and each backlog's length (``backlog_ticks``: ticks in a row
    that two or more inputs waited after the read, how long the authority ran behind)."""
    late = [(px, dz > CORRECTED or floor) for t, px, dz, floor in s.corrections if t >= 1000]
    large = [(px, snap) for px, snap in late if px > s.room.step_px * 1.01]
    runs, run = [], 0
    for w in [*s.waiting, 0]:
        run, done = (run + 1, 0) if w >= 2 else (0, run)
        runs += [done] if done else []
    return {"corrections_px": [px for _, px, _, _ in s.corrections],
            "level_snaps": sum(dz > CORRECTED or floor for _, _, dz, floor in s.corrections),
            "dropped_moves": s.room.dropped_moves, "drained_moves": s.room.drained_moves, "held_steps": s.held_steps,
            "inputs_sent": len(s.sends), "large": len(large), "large_over_30px": sum(px > 30 for px, _ in large),
            "large_with_level_snap": sum(snap for _, snap in large), "minutes": max(0.0, s.now - 1000) / 60000,
            "backlog_ticks": runs}


def attack(rtt: float, jitter: float, loss: float, seed: int, trials: int = 30) -> dict[str, Any]:
    """Stand next to the bandit, press attack: when does the hit show (the snapshot's lower HP: the caption, or the
    sprite hidden at 0), and when do the swing and the confirmed hit's flash show (Feedback)? The bandit's HP is put
    back between trials (the tool's)."""
    rng = random.Random(seed)
    presses = [1000.0 + i * 1500 + rng.uniform(0, 100) for i in range(trials)]
    queued: list[int] = []  # (the meant tick of each swing not sent yet: Arena.act)
    hp_seen: list[tuple[float, float]] = []
    swings: list[float] = []  # (the frame each press swung on: inf when the cooldown refused it)
    flashes: list[float] = []

    def intent(now: float, shown: list[Any]) -> tuple[Any, ...]:
        return (0, 0, "attack", queued.pop(0)) if queued else (0, 0, None)

    def frame(now: float, s: Session) -> None:
        hp_seen.append((now, next(r[1] for r in s.latest["enemies"] if r[0] == BANDIT)))
        flashes.extend(now for _ in s.hits[len(flashes):])  # (a hit confirmed since the last frame flashes now)
        if len(swings) < len(presses) and presses[len(swings)] <= now:  # (a press: the window's next frame reads it)
            tick = s.feedback.press(now / 1000)
            swings.append(now if tick is not None else math.inf)
            if tick is not None:
                queued.append(tick)

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
            "trials": trials, "stale_attacks": room.stale_attacks, "refused_attacks": room.refused_attacks,
            "dropped_actions": room.dropped_actions}


def window_arena() -> Any:
    """mesh_net.demo.Arena without a window: the client's own key, action and send handling."""
    from types import SimpleNamespace  # noqa: PLC0415

    from mesh_net.demo import Arena  # noqa: PLC0415

    keys = SimpleNamespace(**{n: i for i, n in enumerate("W UP S DOWN A LEFT D RIGHT SPACE E ESCAPE F2 R N".split())})
    return Arena(SimpleNamespace(push_handlers=lambda **_kw: None), SimpleNamespace(key=keys))


def walking(rtt: float, jitter: float, loss: float, seed: int, ms: float = 20000) -> dict[str, Any]:
    """The costs of the server's input queue while a player never stops (M4-3): it walks for 20 s, turning between
    left and right every second, and swings about every 600 ms, through the window's own handling (window_arena).
    How many inputs wait in the authority's queue after each tick (``waiting``: ticks it runs behind the newest it
    has) and how long a deep queue lasts; how late a peer sees each step (ms from the input being sent to a peer's
    Playback showing a state that read it); and how long a swing made while walking waits for its confirmation (ms
    from the press to the first frame after a state counting that attack)."""
    rng = random.Random(seed)
    presses, t = [], 1500.0
    while t < ms - 1500:
        presses.append(t)
        t += 600.0 + rng.uniform(-50, 50)
    swung: list[tuple[float, int]] = []  # (press ms, meant tick) of each swing shown
    ran: dict[int, int] = {}  # meant tick -> the tick the authority started that attack (stale ones never start)
    confirmed: list[float] = []
    peer: list[float] = []

    def held(now: float) -> tuple[int, int]:
        return ((1 if (now // 1000) % 2 == 0 else -1), 0) if 1000.0 <= now < ms - 500 else (0, 0)

    def frame(now: float, s: Session) -> None:
        for p in [p for p in presses if now - FRAME_MS < p <= now]:
            tick = s.feedback.press(now / 1000)
            if tick is not None:
                s.arena.act("attack", tick)
                swung.append((p, tick))
        for press, meant in [w for w in swung if w[1] in ran and s.latest["tick"] >= ran[w[1]]]:
            confirmed.append(now - press)  # (the first frame after a state from the tick that started it)
            swung.remove((press, meant))
        s.playback.positions(now / 1000)
        left = next(st for st in reversed(s.playback.states) if st["tick"] <= s.playback.cursor)
        seen = next(r[6] for r in left["players"] if r[0] == s.eid)
        while shown_upto[0] < len(s.sends) and s.sends[shown_upto[0]][1] <= seen:
            sent_at = s.sends[shown_upto[0]][0]
            if 1000.0 <= sent_at < ms - 500:
                peer.append(now - sent_at)
            shown_upto[0] += 1

    shown_upto = [0]
    with coop_room() as room:
        judge_attack = room._may_attack

        def may_attack(p: Any, meant: int) -> bool:
            started = judge_attack(p, meant)
            if started:
                ran[meant] = room.tick
            return started

        room._may_attack = may_attack  # type: ignore[method-assign]
        s = Session(room, rtt, jitter, loss, seed, frame=frame, held=held, arena=window_arena(),
                    setup=lambda room, eid: place(room, eid, 500.0, 256.0, 0))
        s.run(ms)
        walking_ticks = [w for tick, w in zip(range(1, len(s.waiting) + 1), s.waiting) if 1000 <= tick * 50 < ms - 500]
    longest = run = 0
    for w in walking_ticks:
        run = run + 1 if w >= 2 else 0
        longest = max(longest, run)
    tail = walking_ticks[-5 * wire.HZ:]
    return {**queue(s), "waiting": walking_ticks, "max_deep_queue_ticks": longest,
            "waiting_last_5s": [sum(tail) / max(1, len(tail))], "peer_view_ms": peer, "walking_swing_confirmed_ms": confirmed,
            "walking_swings": len(confirmed) + len(swung), "walking_stale": room.stale_attacks,
            "walking_refused": room.refused_attacks}


def judge(s: Session, samples: list[tuple[float, tuple[Any, ...], dict[str, tuple[float, float, float]]]],
          ) -> dict[str, Any]:
    """Per sampled frame (a press there): the hit as the attacker's screen showed it against the authority's hit on the
    tick the press lands, from where it ran it (Session.combat_pose); also with the authority rewinding the targets to
    what the screen showed (lag compensation)."""
    counts = {"view_hit": 0, "view_miss": 0, "looked_hit_missed": 0, "looked_miss_hit": 0, "rewind_disagree": 0,
              "level_looked_ok_refused": 0, "level_looked_refused_ok": 0, "cause_target": 0, "cause_attacker": 0,
              "cause_both": 0}
    for t, own, targets in samples:
        tick = s.landing_tick(t)
        if tick is None or tick not in s.poses:
            continue
        server, pose = s.poses[tick], s.combat_pose(tick)
        seen_hit, seen_level = ask(s.room, own, targets)
        real_hit, real_level = ask(s.room, pose, server["enemies"])
        rewound_hit, _ = ask(s.room, pose, targets)
        counts["view_hit" if seen_hit else "view_miss"] += 1
        counts["looked_hit_missed"] += seen_hit and not real_hit
        counts["looked_miss_hit"] += real_hit and not seen_hit
        counts["rewind_disagree"] += rewound_hit != seen_hit
        level = (seen_hit and not real_hit and seen_level and not real_level) or (
            real_hit and not seen_hit and real_level and not seen_level)
        counts["level_looked_ok_refused"] += seen_hit and not real_hit and seen_level and not real_level
        counts["level_looked_refused_ok"] += real_hit and not seen_hit and real_level and not seen_level
        if seen_hit != real_hit and not level:  # (the floor rule's own are counted above)
            # (the real attacker against the targets as shown agrees with the screen: the targets' motion did it; the
            # attacker as shown against the real targets does: the attacker's; neither alone: both)
            if rewound_hit == seen_hit:
                counts["cause_target"] += 1
            elif ask(s.room, own, server["enemies"])[0] == seen_hit:
                counts["cause_attacker"] += 1
            else:
                counts["cause_both"] += 1
    return counts


GROUND_Y = 122.0  # px: a sprite centre on the crossing's open ground (feet on a navigation row, 3.25 m), south of it
GROUND_ROUTE = (552.0, 664.0)  # px: the bandit's feet walk between these, through the still attacker's hitbox


def swinging(s: Session, presses: list[float]) -> tuple[Callable[[float], None], dict[str, Any]]:
    """Swings pressed at ``presses`` (ms) through the window's own handling (Arena.act, Feedback), and what became of
    them: ``frame(now)`` presses those due; ``done()`` gives, per swing shown, whether the authority ran it, and for
    each hit its swing scored, how long from the press until the window first showed a state of the tick it hit on.
    The bandit is healed before every tick (the tool's: it never dies)."""
    swung: list[tuple[float, int]] = []  # (press ms, meant tick) of each swing shown
    ran: dict[int, int] = {}  # meant tick -> the tick the authority started it
    seen: list[tuple[float, int]] = []  # (frame ms, the latest tick the window has)
    judge_attack = s.room._may_attack

    def may_attack(p: Any, meant: int) -> bool:
        started = judge_attack(p, meant)
        if started:
            ran[meant] = s.room.tick
        return started

    s.room._may_attack = may_attack  # type: ignore[method-assign]

    def frame(now: float) -> None:
        for p in [p for p in presses if now - FRAME_MS < p <= now]:
            tick = s.feedback.press(now / 1000)
            if tick is not None:
                s.arena.act("attack", tick)
                swung.append((p, tick))
        seen.append((now, s.latest["tick"]))

    def done() -> dict[str, Any]:
        starts = sorted((tick, press) for press, meant in swung if (tick := ran.get(meant)) is not None)
        hit_ticks = [t for t in sorted(s.poses) if t - 1 in s.poses and s.poses[t]["hit_seq"] != s.poses[t - 1]["hit_seq"]]
        confirmed = []
        for t in hit_ticks:  # (each hit put down to the latest swing started at or before it, within a hitbox's life)
            press = next((p for start, p in reversed(starts) if start <= t < start + s.room.lifetime), None)
            shown_at = next((now for now, tick in seen if tick >= t), None)
            if press is not None and shown_at is not None:
                confirmed.append(shown_at - press)
        return {"swings": len(swung), "swings_never_run": sum(meant not in ran for _, meant in swung),
                "hit_confirmed_ms": confirmed, "stale_attacks": s.room.stale_attacks,
                "refused_attacks": s.room.refused_attacks, "dropped_actions": s.room.dropped_actions}

    return frame, done


def heal(room: SceneRoom) -> Callable[[int], None]:
    def mover(tick: int) -> None:
        for e in room.enemies.values():
            e.state = TargetState(hp=e.state.max_hp, max_hp=e.state.max_hp)
    return mover


def swing_times(seed: int, ms: float) -> list[float]:
    rng = random.Random(seed)
    presses, t = [], 1500.0
    while t < ms - 1500:
        presses.append(t)
        t += 600.0 + rng.uniform(-50, 50)
    return presses


def target_motion(shown: list[tuple[float, float]], server: list[float], ms: float) -> dict[str, Any]:
    """How the target's motion looked (frame-to-frame x as shown) and how fast it really went (the authority's x a
    tick, while it walked)."""
    xs = [x for x, _ in shown]
    deltas = [q - p for p, q in zip(xs, xs[1:])]
    steps = [abs(q - p) for p, q in zip(server, server[1:])]
    walked = [d for d in steps if d > 1e-6]
    longest = run = 0
    for d in deltas:
        run = run + 1 if abs(d) <= 1e-6 else 0
        longest = max(longest, run)
    return {"target_frames": len(deltas), "target_frozen": sum(abs(d) <= 1e-6 for d in deltas),
            "max_target_freeze_frames": longest,
            "target_px_per_s": [sum(steps) / max(1e-9, len(steps) / wire.HZ)],
            "target_step_px_max": [max(walked, default=0.0)],
            "target_snaps_over_2x_step": sum(abs(d) > 2 * max(walked, default=0.0) * wire.HZ / 60 + 0.01 for d in deltas)}


def moving_target(rtt: float, jitter: float, loss: float, seed: int, speed: float, ms: float = 12000) -> dict[str, Any]:
    """HD-2D, the crossing's open ground: a still attacker facing east, and the bandit walking its FloorRoute (at
    ``speed`` px/s as authored, no wait) east and west through the attacker's hitbox, on the authority (M4-4); the
    window shows it through Playback.enemies. Fairness (every frame a hypothetical press), real swings about every
    600 ms (shown, run, hits confirmed), and how the target's motion looks."""
    samples: list[tuple[float, tuple[Any, ...], dict[str, tuple[float, float, float]]]] = []
    shown_x: list[tuple[float, float]] = []
    route = {"route": [[GROUND_ROUTE[0], GROUND_Y - 18, 0.0], [GROUND_ROUTE[1], GROUND_Y - 18, 0.0]], "speed": speed,
             "wait": 0.0}
    with stairs_room(GROUND_ROUTE[0], GROUND_Y, route) as room:
        presses = swing_times(seed, ms)
        holder: dict[str, Any] = {}

        def frame(now: float, s: Session) -> None:
            holder["frame"](now)
            if now < 1000:
                return
            target = s.enemies_shown(now)
            own = s.own_shown
            samples.append((now, (own[0], own[1], own[2], 0), target))
            shown_x.append((target[BANDIT][0], now))

        s = Session(room, rtt, jitter, loss, seed, mover=heal(room), frame=frame, held=lambda now: (0, 0),
                    arena=window_arena(), setup=lambda room, eid: place(room, eid, 520.0, GROUND_Y, 0))
        holder["frame"], done = swinging(s, presses)
        s.run(ms)
        server_x = [s.poses[t]["enemies"][BANDIT][0] for t in sorted(s.poses) if t * 1000 / wire.HZ >= 1000]
        return {**judge(s, samples), **done(), **target_motion(shown_x, server_x, ms)}


def moving_both(rtt: float, jitter: float, loss: float, seed: int, ms: float = 12000) -> dict[str, Any]:
    """HD-2D, the open ground: the attacker walks up to the walking bandit and away (east and west, turning every
    700 ms, facing the way it walks; its window predicting it, M4-3) while the bandit walks its FloorRoute (70 px/s)
    through the same stretch. Fairness by cause, swings made walking (shown, run, hits confirmed), and the queue."""
    samples: list[tuple[float, tuple[Any, ...], dict[str, tuple[float, float, float]]]] = []
    route = {"route": [[GROUND_ROUTE[0], GROUND_Y - 18, 0.0], [GROUND_ROUTE[1], GROUND_Y - 18, 0.0]], "speed": 70.0,
             "wait": 0.0}

    def held(now: float) -> tuple[int, int]:
        return (1 if (now // 700) % 2 == 0 else -1), 0

    with stairs_room(GROUND_ROUTE[0], GROUND_Y, route) as room:
        holder: dict[str, Any] = {}

        def frame(now: float, s: Session) -> None:
            holder["frame"](now)
            if now >= 1000:  # (seen: where the window shows itself, facing the way it is walking)
                x, y, z, _floor = s.own_shown
                samples.append((now, (x, y, z, facing_of(*held(now), 0)), s.enemies_shown(now)))

        s = Session(room, rtt, jitter, loss, seed, mover=heal(room), frame=frame, held=held, arena=window_arena(),
                    setup=lambda room, eid: place(room, eid, 500.0, GROUND_Y, 0))
        holder["frame"], done = swinging(s, swing_times(seed, ms))
        s.run(ms)
        return {**judge(s, samples), **done(), **queue(s)}


STAIRS_X = 328.0  # px: the bandit's feet on the west stairs (a navigation column, clear of their east edge)
STAIRS_ROUTE = ((152.0, 4.0), (264.0, 60.0))  # (feet y, elevation) px: near their foot and near their top


def stairs_moving(rtt: float, jitter: float, loss: float, seed: int, ms: float = 12000) -> dict[str, Any]:
    """HD-2D: the bandit walks its FloorRoute (70 px/s) up and down the west stairs while a still attacker on the
    ground beside their east edge faces it, its hitbox over the stretch where the bandit climbs out of same_level's
    reach (1.5 m: BODY). Fairness by cause (the floor rule's share now from the target's motion), real swings."""
    samples: list[tuple[float, tuple[Any, ...], dict[str, tuple[float, float, float]]]] = []
    (y0, z0), (y1, z1) = STAIRS_ROUTE
    route = {"route": [[STAIRS_X, y0, z0], [STAIRS_X, y1, z1]], "speed": 70.0, "wait": 0.0}
    with stairs_room(STAIRS_X, y0 + 18, route) as room:
        holder: dict[str, Any] = {}

        def frame(now: float, s: Session) -> None:
            holder["frame"](now)
            if now >= 1000:
                own = s.own_shown
                samples.append((now, (own[0], own[1], own[2], 2), s.enemies_shown(now)))

        s = Session(room, rtt, jitter, loss, seed, mover=heal(room), frame=frame, held=lambda now: (0, 0),
                    arena=window_arena(), setup=lambda room, eid: place(room, eid, 368.0, 240.0, 2))
        holder["frame"], done = swinging(s, swing_times(seed, ms))
        s.run(ms)
        heights = [s.poses[t]["enemies"][BANDIT][2] for t in s.poses]
        floors = sorted({f for t in s.poses if (f := s.poses[t]["enemy_floors"][BANDIT])})
        return {**judge(s, samples), **done(), "floors_walked": floors, "max_elevation_px": max(heights)}


def moving_attacker(rtt: float, jitter: float, loss: float, seed: int, ms: float = 12000) -> dict[str, Any]:
    """Today's real case: the attacker walks up to the (still) bandit and away again, its screen showing itself at the
    latest snapshot. Fairness only (the target never moves)."""
    samples: list[tuple[float, tuple[Any, ...], dict[str, tuple[float, float, float]]]] = []

    def held(now: float) -> tuple[int, int]:
        return (1 if (now // 700) % 2 == 0 else -1), 0

    def intent(now: float, shown: list[Any]) -> tuple[int, int, None]:
        return *held(now), None

    with coop_room() as room:
        bandit = room.enemies[BANDIT].body
        target = {BANDIT: (bandit.center_x, bandit.center_y, 0.0)}

        def frame(now: float, s: Session) -> None:
            if now >= 1000:  # (seen: where the window shows itself, facing the way it is walking)
                x, y, z, _floor = s.own_shown
                samples.append((now, (x, y, z, facing_of(*held(now), 0)), target))

        s = Session(room, rtt, jitter, loss, seed, intent=intent, frame=frame, held=held,
                    setup=lambda room, eid: place(room, eid, 500.0, 256.0, 0))
        s.run(ms)
        return {**judge(s, samples), **queue(s)}


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
    p.seq = p.ack = p.dx = p.dy = 0  # (the session's own inputs count from 1; it stands still until they come)
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
            if now >= 1000:  # (seen: where the window shows itself, facing east as it walks)
                x, y, z, _floor = s.own_shown
                samples.append((now, (x, y, z, facing_of(1, heading["dy"], 0)), target))

        s = Session(room, rtt, jitter, loss, seed, intent=intent, frame=frame, setup=to_stairs_edge,
                    held=lambda now: (1, heading["dy"]))
        s.run(ms)
        result = {**judge(s, samples), **queue(s)}
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
                                                 / max(1, n), 1),
              # (M4-4: every disagreement put down to one cause: the floor rule (above), the target's motion, the
              # attacker's, or both together)
              "target_caused_disagree_pct": round(100 * c["cause_target"] / max(1, n), 1),
              "attacker_caused_disagree_pct": round(100 * c["cause_attacker"] / max(1, n), 1),
              "both_caused_disagree_pct": round(100 * c["cause_both"] / max(1, n), 1)}
    if "target_frames" in c:
        result.update({"target_frames_frozen_pct": round(100 * c["target_frozen"] / max(1, c["target_frames"]), 1),
                       "target_longest_freeze_ms": round(c["max_target_freeze_frames"] * FRAME_MS),
                       "target_snaps_over_2x_step": c["target_snaps_over_2x_step"],
                       "target_px_per_s": round(sum(c["target_px_per_s"]) / len(c["target_px_per_s"]), 1),
                       "target_step_px_max": round(max(c["target_step_px_max"]), 2)})
    if "swings" in c:  # (real swings: owner condition 7, never hidden)
        result.update({"swings": c["swings"], "swings_never_run": c["swings_never_run"],
                       "hit_confirmed_ms": summary(c["hit_confirmed_ms"]), "stale_attacks": c["stale_attacks"],
                       "refused_attacks": c["refused_attacks"], "dropped_actions": c["dropped_actions"]})
    if "floors_walked" in c:
        result.update({"floors_walked": sorted(set(c["floors_walked"])), "max_elevation_px": c["max_elevation_px"]})
    if "corrections_px" in c:
        result["prediction"] = corrections(c)
    return result


def walking_costs(w: dict[str, Any]) -> dict[str, Any]:
    """walking's pooled results: the queue's depth while walking, how late a peer sees it, swings confirmed."""
    return {"waiting": summary([float(v) for v in w["waiting"]]),
            "max_deep_queue_ticks": w["max_deep_queue_ticks"],
            "waiting_last_5s_mean": round(max(w["waiting_last_5s"]), 2),
            "peer_view_ms": summary(w["peer_view_ms"]), "walking_swing_confirmed_ms": summary(w["walking_swing_confirmed_ms"]),
            "walking_swings": w["walking_swings"], "walking_stale": w["walking_stale"], "walking_refused": w["walking_refused"],
            "prediction": corrections(w)}


def corrections(c: dict[str, Any]) -> dict[str, Any]:
    """The prediction's corrections (M4-3): p95 over every reconciliation (one per snapshot), and the ones that moved
    the avatar (over CORRECTED px): how many, how far; elevation or floor snaps; and the queue's drops and holds."""
    px = c["corrections_px"]
    moved = [v for v in px if v > CORRECTED]
    return {"reconciliations": len(px), "p95_px": round(pct(px, 0.95), 2) if px else 0.0, "corrections": len(moved),
            "corrected_px": summary(moved), "level_snaps": c["level_snaps"], "dropped_moves": c["dropped_moves"],
            "drained_moves": c.get("drained_moves", 0), "held_steps": c["held_steps"], "large": c["large"],
            "large_per_minute": round(c["large"] / max(1e-9, c["minutes"]), 2), "large_over_30px": c["large_over_30px"],
            "large_with_level_snap": c["large_with_level_snap"], "backlog_ticks": summary(c["backlog_ticks"])}


def measure(seed: int = 7, sessions: int = 6) -> dict[str, Any]:
    rows = []
    for i, profile in enumerate((*PROFILES, JITTER_ONLY)):
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
                         "most_inputs_in_one_tick": m["max_inputs_in_one_tick"], "prediction": corrections(m)},
            "attack": {"swing_visible_ms": summary(a["swing_visible_ms"]), "hit_confirmed_ms": summary(a["hit_confirmed_ms"]),
                       "hit_flash_ms": summary(a["hit_flash_ms"]), "hits_seen": f"{len(a['hit_confirmed_ms'])}/{a['trials']}",
                       # (attacks the server did not run: never hidden, owner decision of 2026-11-24, condition 7)
                       "stale_attacks": a["stale_attacks"], "refused_attacks": a["refused_attacks"],
                       "dropped_actions": a["dropped_actions"]},
            "moving_target_70": fairness(pooled(moving_target, seeds, *profile, 70.0)),
            "moving_target_150": fairness(pooled(moving_target, seeds, *profile, 150.0)),
            "moving_both": fairness(pooled(moving_both, seeds, *profile)),
            "stairs_moving": fairness(pooled(stairs_moving, seeds, *profile)),
            "moving_attacker": fairness(pooled(moving_attacker, seeds, *profile)),
            "stairs": fairness(pooled(stairs, seeds, *profile)),
            "walking": walking_costs(pooled(walking, seeds, *profile))})
    return {"seed": seed, "sessions_per_profile": sessions, "frame_ms": round(FRAME_MS, 2), "rto_ms": RTO_MS,
            "hz": wire.HZ, "depth": scene_room.DEPTH, "hold": scene_room.HOLD, "drain": scene_room.DRAIN, "profiles": rows}


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


def queue_of(args: argparse.Namespace) -> tuple[int, int, int]:
    """The queue settings to measure, as mesh_net.server.queue_from takes them: each knob given (``--depth``,
    ``--hold``, ``--drain``), else ``--queue``'s preset's, else the game's default; checked (ValueError)."""
    return scene_room.queue_settings(args.depth, args.hold, args.drain, preset=args.queue)


def main() -> None:
    global RTO_MS
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seeds", type=int, nargs="+", default=[7, 8, 9], help="one run per seed; the spread is "
                                                                                 "reported as [lowest, highest]")
    parser.add_argument("--sessions", type=int, default=24, help="sessions pooled per latency profile")
    parser.add_argument("--rto", type=float, default=RTO_MS, help="a lost segment arrives RTT + this many ms later")
    parser.add_argument("--hz", type=int, default=wire.HZ, help="what-if: the authority's tick and the client's send "
                                                                "rate (the game's is mesh_net.protocol.HZ)")
    parser.add_argument("--depth", type=int, help="what-if: the server's input queue (the game's is "
                                                  "mesh_net.scene_room.DEPTH)")
    parser.add_argument("--hold", type=int, help="what-if: mesh_net.scene_room.HOLD")
    parser.add_argument("--queue", choices=sorted(scene_room.QUEUE_PRESETS), help="a preset (mesh_net.scene_room."
                        "QUEUE_PRESETS); --depth, --hold and --drain given beat its values, as the server's flags do")
    parser.add_argument("--drain", type=int, help="what-if: mesh_net.scene_room.DRAIN (0: off)")
    parser.add_argument("--json", help="also write the full result here")
    args = parser.parse_args()
    RTO_MS = args.rto
    depth, hold, drain = queue_of(args)  # (refused here, before minutes of work)
    with (mock.patch.object(wire, "HZ", args.hz), mock.patch.object(scene_room, "DEPTH", depth),
          mock.patch.object(scene_room, "HOLD", hold), mock.patch.object(scene_room, "DRAIN", drain)):
        runs = [measure(seed, args.sessions) for seed in args.seeds]
        result = {"seeds": args.seeds, "range": ranges(runs), "runs": runs, "snapshot_bytes": snapshot_bytes()}
    text = json.dumps(result, indent=1)
    if args.json:
        Path(args.json).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
