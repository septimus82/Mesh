"""M4-3: the server reads one input a tick (owner decision OD11) and a window predicts its own avatar (OD3).

- The queue (mesh_net.scene_room.SceneRoom.input and step): one input read a tick, the oldest; at most DEPTH waiting, a
  full queue dropping its oldest direction but never an attack, a use or a take (they run when a later input is read);
  ``ack`` is the input the tick read; with nothing waiting the last direction is walked on until HOLD ticks after it,
  then the body stops. An input's actions run from where the player stood before its step: where the window showed it.
- The prediction (mesh_net.scene_room.Prediction): each input walks the avatar at once through SceneRoom.walk (one
  step for both sides: tests/test_hd2d_net_parity.py); each snapshot puts it back on the server's row and walks again
  what the server has not read; elevation and floor take the server's at once, x/y fades; nothing hidden is carried.
  Started anew at a welcome (a resume's too) and when a room shows; stopped at an enter and at a session's end.
- The owner's safeguards, on the probe's virtual clock and TCP link model (tooling/m4_latency_probe.py), seeds 7, 8 and 9:
  quick direction reversals, key release and short taps, attacks mashed while walking, the cooldown, jitter, loss
  bursts, a server stall of more than a second and a network outage of 1.5 s. Every tick the server walks at most one
  step, only a direction an input gave (read that tick, or walked on within HOLD), its way; it stops once the keys are
  let go; no attack starts twice or without a swing shown; and the window ends exactly where the server has it.
- Feedback's reckoning rides out a TCP retransmission hold and follows a real server stall (M4-2 review follow-up).
"""

from __future__ import annotations

import asyncio
import math
import random
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from engine.combat_model import TargetState
from mesh_net import protocol as wire
from mesh_net import world_client
from mesh_net.demo import Arena
from mesh_net.scene_client import SceneArena
from mesh_net.scene_room import (
    DEPTH,
    HOLD,
    SMOOTH_S,
    Feedback,
    Prediction,
    SceneRoom,
)
from mesh_net.world_client import WorldArena
from tests.test_mesh_net_world import Driver, make_world
from tooling.m4_latency_probe import (
    BANDIT,
    CORRECTED,
    FRAME_MS,
    JITTER_ONLY,
    PROFILES,
    RTO_MS,
    Session,
    coop_room,
    place,
    stairs_room,
    to_stairs_edge,
)

pytestmark = pytest.mark.integration  # (rooms built in folders)

REPO = Path(__file__).resolve().parents[1]
OPEN = (200.0, 200.0)  # px: open floor in the co-op room, a few steps clear every way
SEEDS = (7, 8, 9)


def send(room: SceneRoom, eid: int, seq: int, dx: int, dy: int, action: str | None = None) -> None:
    room.input(eid, wire.input_frame(eid, seq, dx, dy, room.tick, action))


def at(room: SceneRoom, eid: int) -> tuple[float, float]:
    b = room.players[eid].body
    return b.center_x, b.center_y


# --- the queue (OD11) --------------------------------------------------------------------------------------------


def test_the_server_reads_one_input_a_tick_oldest_first_and_acks_it() -> None:
    """Two inputs in one tick are two ticks of walking, one step each, in the order sent; each tick's ``ack`` is the
    input it read."""
    with coop_room() as room:
        eid = room.join()
        place(room, eid, *OPEN, 0)
        p, step = room.players[eid], room.step_px
        send(room, eid, 1, 1, 0)
        send(room, eid, 2, 0, 1)
        room.step()
        assert p.ack == 1 and at(room, eid) == (OPEN[0] + step, OPEN[1]) and p.facing == 0
        room.step()
        assert p.ack == 2 and at(room, eid) == (OPEN[0] + step, OPEN[1] + step) and p.facing == 1
        assert not p.moves


def test_a_full_queue_keeps_the_newest_direction_and_every_action() -> None:
    """DEPTH waiting and more come (a burst after a stall): the oldest directions are dropped (counted), never their
    actions: an attack and a use carried by dropped inputs run on the tick that reads a later input. Never more than one
    step a tick."""
    with coop_room() as room:
        eid = room.join()
        place(room, eid, 568.0, 256.0, 0)  # (next to the bandit, facing it)
        p, step = room.players[eid], room.step_px
        room.enemies[BANDIT].state = TargetState(hp=100.0, max_hp=100.0)
        burst = [(1, 0, -1, "attack"), (2, 0, -1, "use"), (3, 0, 1, None), (4, 0, 0, None), (5, 0, 1, None)]
        for seq, dx, dy, action in burst:
            send(room, eid, seq, dx, dy, action)
        assert DEPTH == 2 and [m[0] for m in p.moves] == [4, 5], "the newest two wait"
        assert room.dropped_moves == len(burst) - DEPTH and room.dropped_actions == 0
        before = at(room, eid)
        room.step()
        assert p.ack == 4 and p.attack_seq == 1 and room.enemies[BANDIT].hit_seq == 1, "the dropped input's attack ran"
        assert p.actions == [] and room.used == set(), "its use ran too (out of the lever's reach: nothing to use)"
        assert at(room, eid) == before, "input 4 read: it walks nowhere (inputs 1-3 never walked)"
        room.step()
        assert p.ack == 5 and at(room, eid) == (before[0], before[1] + step), "then input 5: one step"


def test_a_standing_player_gets_its_queues_tick_back_and_nothing_else_changes() -> None:
    """Two still inputs waiting (the queue a tick deep while the player stands): the older is dropped and the newer
    read, so its attack runs a tick sooner; nothing walks. A queue with a step in it is never shortened."""
    with coop_room() as room:
        eid = room.join()
        place(room, eid, 568.0, 256.0, 0)  # (next to the bandit, facing it)
        p = room.players[eid]
        room.enemies[BANDIT].state = TargetState(hp=100.0, max_hp=100.0)
        send(room, eid, 1, 0, 0, "attack")
        send(room, eid, 2, 0, 0)
        still = at(room, eid)
        room.step()
        assert p.ack == 2 and p.attack_seq == 1 and at(room, eid) == still and room.dropped_moves == 0
        place(room, eid, *OPEN, 0)
        for seq, (dx, dy) in ((3, (0, 0)), (4, (1, 0))):
            send(room, eid, seq, dx, dy)
        room.step()
        assert p.ack == 3 and at(room, eid) == OPEN, "a still input before a step is read: never skipped"
        room.step()
        assert p.ack == 4 and at(room, eid) == (OPEN[0] + room.step_px, OPEN[1])
        for seq, (dx, dy) in ((5, (1, 0)), (6, (0, 0))):
            send(room, eid, seq, dx, dy)
        room.step()
        assert p.ack == 5 and at(room, eid) == (OPEN[0] + 2 * room.step_px, OPEN[1]), "a step is never dropped"


def test_an_empty_queue_walks_the_last_direction_until_hold_then_stops() -> None:
    """One input and nothing after it: walked HOLD ticks (its own included: today's lease), then the body stops;
    ``ack`` stays the input read."""
    with coop_room() as room:
        eid = room.join()
        place(room, eid, *OPEN, 0)
        send(room, eid, 1, 1, 0)
        xs = []
        for _ in range(HOLD + 3):
            room.step()
            xs.append(at(room, eid)[0])
        assert xs == [OPEN[0] + room.step_px * min(i, HOLD) for i in range(1, HOLD + 4)]
        assert room.players[eid].ack == 1


def test_an_inputs_actions_run_from_where_the_window_showed_the_player() -> None:
    """Walking right, the attack rides input 3: it runs on the tick that reads input 3, its hitbox made ``range`` ahead
    of where the player stood after input 2 (where a predicting window showed it when Space was pressed), and the
    step of input 3 follows."""
    with coop_room() as room:
        eid = room.join()
        place(room, eid, *OPEN, 0)
        made: list[float] = []
        attack = room._attack
        room._attack = lambda p: (made.append(p.body.center_x), attack(p))[1]  # type: ignore[method-assign]
        for seq, action in ((1, None), (2, None), (3, "attack")):  # (one a tick, as a window sends them)
            send(room, eid, seq, 1, 0, action)
            room.step()
        assert made == [OPEN[0] + 2 * room.step_px] and at(room, eid)[0] == OPEN[0] + 3 * room.step_px


# --- the prediction (OD3) ----------------------------------------------------------------------------------------


def row(room: SceneRoom, eid: int) -> list[Any]:
    return next(r for r in room.snapshot()["players"] if r[0] == eid)


def test_each_snapshot_puts_the_avatar_back_and_walks_what_the_server_has_not_read() -> None:
    """Three inputs walked at once; a snapshot that read one of them changes nothing; one where the server dropped the
    second (a full queue) and read the third puts the avatar a step back: a correction of one step."""
    with coop_room() as room:
        eid = room.join()
        place(room, eid, *OPEN, 0)
        prediction = Prediction()
        prediction.start(room, room.snapshot(), eid)
        for seq in (1, 2, 3):
            assert prediction.next((1, 0)) == (1, 0)
            prediction.sent(seq)
        step = room.step_px
        assert prediction.body is not None and prediction.body.center_x == OPEN[0] + 3 * step
        send(room, eid, 1, 1, 0)
        room.step()
        assert prediction.reconcile(room.snapshot(), eid) == (0.0, 0.0, False) and len(prediction.inputs) == 2
        assert prediction.body.center_x == OPEN[0] + 3 * step
        room.players[eid].ack = 3  # (2 dropped from a full queue, 3 read: one step fewer than sent)
        moved, dz, floor = prediction.reconcile(room.snapshot(), eid)
        assert moved == pytest.approx(2 * step) and not prediction.inputs
        assert prediction.body.center_x == OPEN[0] + step
        x, *_ = prediction.shown(0.0)
        assert x == pytest.approx(OPEN[0] + 3 * step), "the correction fades: shown where it was"
        x, *_ = prediction.shown(SMOOTH_S / 2)
        assert x == pytest.approx(OPEN[0] + 2 * step)
        x, *_ = prediction.shown(SMOOTH_S / 2)
        assert x == OPEN[0] + step, "and is gone after SMOOTH_S, exactly"


def test_a_press_builds_the_next_input_at_once_and_the_send_carries_it() -> None:
    """A direction pressed between two sends walks the avatar on that frame; the next send carries that input (not
    another); a second press before it goes builds nothing more: one input, one step, a send."""
    with coop_room() as room:
        eid = room.join()
        place(room, eid, *OPEN, 0)
        prediction = Prediction()
        prediction.start(room, room.snapshot(), eid)
        prediction.press((0, 1))
        assert prediction.body is not None and prediction.body.center_y == OPEN[1] + room.step_px
        prediction.press((1, 0))
        assert prediction.next((1, 0)) == (0, 1) and len(prediction.inputs) == 1
        prediction.sent(1)
        assert prediction.next((1, 0)) == (1, 0) and len(prediction.inputs) == 2, "then the keys held"


def test_every_input_carries_the_tick_the_window_reckons() -> None:
    """One estimate of the room's tick (Feedback.tick): a movement input carries the tick reckoned when it goes, an
    attack the tick its swing reckoned (M4-2 sent the last snapshot's tick + 1, half a round trip stale)."""
    keys = SimpleNamespace(**{n: i for i, n in enumerate("W UP S DOWN A LEFT D RIGHT SPACE E ESCAPE F2 R N".split())})
    arena: Any = Arena(SimpleNamespace(push_handlers=lambda **_kw: None), SimpleNamespace(key=keys))
    now = [10.0]
    arena.clock, arena.feedback = lambda: now[0], Feedback()
    arena.feedback.baseline({"tick": 100, "players": [], "enemies": []}, 10, 10.0)  # tick 100 seen at 10 s
    now[0] = 10.26
    assert arena.outgoing() == ((0, 0), None, 105)
    arena.act("attack", 103)
    arena.press(keys.RIGHT, 0)
    assert arena.outgoing() == ((1, 0), "attack", 103)


def test_an_hd2d_correction_snaps_elevation_and_floor_and_fades_only_x_and_y() -> None:
    """On the floors demo's stairs: a snapshot that puts the avatar on another floor at another height shows that
    floor and height on the very next frame (never a body between floors), while its x/y fades."""
    with stairs_room() as room:
        eid = room.join()
        ground = row(room, eid)
        to_stairs_edge(room, eid)
        stairs = row(room, eid)
        assert ground[5] == "ground" and stairs[5] == "crossing/col_stairs_west" and stairs[4] > 10.0
        prediction = Prediction()
        prediction.start(room, {**room.snapshot(), "players": [[*ground[:6], 0, 0]]}, eid)
        moved, dz, floor = prediction.reconcile({**room.snapshot(), "players": [[*stairs[:6], 0, 0]]}, eid)
        assert moved > 0 and dz == pytest.approx(stairs[4] - ground[4]) and floor
        x, y, z, shown_floor = prediction.shown(0.0)
        assert (z, shown_floor) == (stairs[4], stairs[5]), "elevation and floor: the server's at once"
        assert (x, y) == pytest.approx((ground[1], ground[2])), "x/y: where it was, fading"
        assert prediction.shown(SMOOTH_S)[:2] == (stairs[1], stairs[2])


def test_hidden_solver_state_is_never_carried_and_the_prediction_converges() -> None:
    """The floor solver keeps per-body state that is not on the wire (``mesh_hd2d_deep_cap``, escaping deep water):
    every reconciliation rebuilds the avatar from the server's row, so none of it survives into a replay, and once the
    server's walk and the window's agree again the window is exactly where the server is. (Online rooms refuse such
    water today: owner decision D4. The disagreement is made here by a solid only the server has.)"""
    with coop_room() as room:
        eid = room.join()
        place(room, eid, *OPEN, 0)
        prediction = Prediction()
        prediction.start(room, room.snapshot(), eid)
        assert prediction.body is not None
        prediction.body.mesh_hd2d_deep_cap = 0.3  # type: ignore[attr-defined]
        wall = SimpleNamespace(center_x=OPEN[0] + 30.0, center_y=OPEN[1], width=8.0, height=64.0, mesh_entity_data={})
        solids = room.solids
        room.solids = lambda state=None: solids(state) + ([wall] if state is None else [])  # type: ignore[method-assign]
        seq = 0
        for _ in range(8):  # the server stops at the wall; the window walks through it
            seq += 1
            prediction.next((1, 0))
            prediction.sent(seq)
            send(room, eid, seq, 1, 0)
            room.step()
            prediction.reconcile(room.snapshot(), eid)
        assert not hasattr(prediction.body, "mesh_hd2d_deep_cap"), "rebuilt from the row: nothing hidden carried"
        assert prediction.body.center_x < OPEN[0] + 30.0, "put back on the server's side of the wall"
        room.solids = solids  # type: ignore[method-assign]
        for _ in range(3):  # (agreeing again: the inputs left are read)
            room.step()
            prediction.reconcile(room.snapshot(), eid)
        assert (prediction.body.center_x, prediction.body.center_y) == tuple(row(room, eid)[1:3])
        assert prediction.shown(SMOOTH_S)[:2] == tuple(row(room, eid)[1:3])


# --- the buffers: welcome, enter, session end ------------------------------------------------------------------


def test_a_resume_walks_nothing_from_before_it() -> None:
    """N6: a player leaving with inputs waiting and a direction held comes back still: the server walks nothing it
    was sent before (``leave`` empties the queue), counts its acks anew, and takes the new session's inputs from seq 1;
    the window's welcome starts its prediction anew from the row, nothing from the last session walked again."""
    with coop_room() as room:
        eid = room.join()
        place(room, eid, *OPEN, 0)
        for seq in (1, 2, 3):
            send(room, eid, seq, 1, 0)
        room.step()
        player = room.leave(eid)
        assert not player.moves and (player.dx, player.dy, player.held, player.ack) == (0, 0, HOLD, 0)
        back = room.join(player)
        still = at(room, back)
        for _ in range(HOLD + 2):
            room.step()
        assert at(room, back) == still and room.players[back].ack == 0
        arena: Any = SimpleNamespace(feedback=Feedback(), prediction=Prediction(), view=SimpleNamespace(room=room),
                                     clock=lambda: 9.0)
        arena.prediction.start(room, room.snapshot(), back)
        for seq in (4, 5, 6):  # (the last session's: never acknowledged)
            arena.prediction.next((1, 0))
            arena.prediction.sent(seq)
        SceneArena.on_state(arena, room.snapshot(), back, True)  # the resumed session's welcome
        assert not arena.prediction.inputs and arena.prediction.body.center_x == still[0]
        send(room, back, 1, 1, 0)
        room.step()
        assert room.players[back].ack == 1 and at(room, back)[0] == still[0] + room.step_px


def test_an_n7_resume_comes_back_still() -> None:
    """N7: a player retained with inputs waiting resumes into its room standing still, its queue empty."""
    world = make_world()
    d = Driver(world)
    a, token = d.join()
    d.place(a, 300.0, 256.0)
    d.send(a, 1, 0)
    d.send(a, 1, 0)
    d.step()
    world.disconnect(a)
    pid, _ = d.join(token)
    assert pid == a and not d.player(a).moves and d.player(a).ack == 0
    still = d.at(a)
    d.step(HOLD + 2)
    assert d.at(a) == still


def test_an_n7_transfer_walks_nothing_into_the_new_room() -> None:
    """Inputs waiting and in flight when a door transfers the player: the new room walks none of them (a new body,
    and frames naming the old room dropped); the window stops predicting at the enter and starts anew, from the
    enter's row, when the room shows: nothing it sent in the last room is walked again."""
    world = make_world()
    d = Driver(world)
    a, _ = d.join()
    d.ask(a, "create")
    old, old_eid = d.m(a).instance, d.m(a).eid
    d.place(a, 640.0, 256.0)
    for _ in range(8):
        d.send(a, 1, 0)
        d.send(a, 1, 0)  # (two a tick: the queue full)
        d.w.step()
        if d.m(a).instance != old:
            break
    assert d.room(a).key != "start" and not d.player(a).moves and d.player(a).ack == 0
    arrived = d.at(a)
    for _ in range(4):  # still naming the old room: in flight across the transfer
        d.send(a, 1, 0, room=old, entity=old_eid)
    d.step(HOLD + 2)
    assert d.at(a) == arrived and d.player(a).ack == 0, "nothing walked into the new room"

    enter = next(f for f in d.frames(a, "enter") if f["room"] == d.m(a).instance)
    hub = world.defs["start"].proto
    ids = {k: df.proto.identity for k, df in world.defs.items()}
    shown: list[Any] = []

    class View:  # (WorldArena.draw builds one when the room shows: here it records where the own avatar is drawn)
        def __init__(self, *_args: Any) -> None:
            pass

        def sync(self, state: Any, positions: dict[int, Any], own: Any, dt: float) -> None:
            shown.append(positions.get(own))

        def draw(self, dt: float) -> None:
            pass

    window = SimpleNamespace(scene_controller=SimpleNamespace(room_path="x"), game_state_controller=None,
                             load_scene=lambda path: None, clear=lambda color: None)
    arena: Any = SimpleNamespace(identities=ids, defs=world.defs, room=old, key="start", entity=old_eid, state=None,
                                 playback=None, pending=None, phase="playing", feedback=Feedback(),
                                 prediction=Prediction(), seq=0, actions=[], view=None, shown=old, window=window,
                                 notice=None, loads=[], arcade=None, note=lambda e: None, refusal=None, request=None,
                                 connected=True, last=None, status="")
    hub_state = {**enter["state"], "players": [[old_eid, 640.0, 256.0, 0, 0, None, 0, 0]], "scene": hub.identity}
    arena.prediction.start(hub, hub_state, old_eid)
    for seq in (1, 2, 3):  # sent in the last room, never acknowledged there
        arena.prediction.next((1, 0))
        arena.prediction.sent(seq)
    arena.seq = 3
    WorldArena.on_frame(arena, enter, 1.0)
    assert arena.prediction.body is None and not arena.prediction.inputs, "stopped at the enter"
    arena.prediction.press((1, 0))  # (a key while the room loads: nothing predicted, nothing built)
    assert not arena.prediction.inputs
    original = world_client.SceneView
    world_client.SceneView = View  # type: ignore[misc,assignment]
    try:
        WorldArena.draw(arena, 1.1)  # the room shows
    finally:
        world_client.SceneView = original  # type: ignore[misc]
    own = next(r for r in enter["state"]["players"] if r[0] == enter["entity"])
    assert arena.prediction.body is not None and not arena.prediction.inputs
    assert shown == [(own[1], own[2], own[4], own[5])], "drawn at the enter's row: nothing from the last room"


def test_a_sessions_end_stops_the_prediction() -> None:
    """Arena.session and WorldArena.session: when a session ends (its connection fails here), the prediction stops
    with its unacknowledged inputs: none is walked again in a resumed session."""
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]  # (nothing listens there once closed)
    keys = SimpleNamespace(**{n: i for i, n in enumerate("W UP S DOWN A LEFT D RIGHT SPACE E ESCAPE F2 R N".split())})
    with coop_room() as room:
        eid = room.join()
        for make in ("scene", "world"):
            arena: Any = Arena(SimpleNamespace(push_handlers=lambda **_kw: None), SimpleNamespace(key=keys))
            arena.prediction = Prediction()
            arena.prediction.start(room, room.snapshot(), eid)
            arena.prediction.next((1, 0))
            if make == "scene":
                asyncio.run(Arena.session(arena, port))
            else:
                arena.__dict__.update(port=None, character=None, note=lambda _e: None, phase="playing", room="start:1",
                                      pending=None, requests=[])
                asyncio.run(WorldArena.session(arena, port))
            assert arena.prediction.body is None and not arena.prediction.inputs, make


# --- the owner's safeguards, on the virtual clock ---------------------------------------------------------------


Held = Callable[[float], tuple[int, int]]


def reversals(seed: int) -> Held:
    """Direction keys changed every 20-70 ms (faster than the tick) for 3 s, now and then up or down, then let go."""
    rng, t, changes = random.Random(seed), 1000.0, []
    while t < 4000.0:
        changes.append((t, rng.choice([(1, 0), (-1, 0), (1, 0), (-1, 0), (0, 1), (0, -1)])))
        t += rng.uniform(20.0, 70.0)

    def held(now: float) -> tuple[int, int]:
        if not 1000.0 <= now < 4000.0:
            return 0, 0
        return next(d for start, d in reversed(changes) if start <= now)

    return held


def holds(now: float) -> tuple[int, int]:
    """Right 400 ms, up 300 ms, a 30 ms tap left (shorter than a send), then right again 600 ms: each let go."""
    for start, end, d in ((1000.0, 1400.0, (1, 0)), (2000.0, 2300.0, (0, 1)), (3000.0, 3030.0, (-1, 0)),
                          (3500.0, 4100.0, (1, 0))):
        if start <= now < end:
            return d
    return 0, 0


def mash(seed: int) -> list[float]:
    rng, t, found = random.Random(seed), 1000.0, []
    while t < 4000.0:
        found.append(t)
        t += 70.0 + rng.uniform(-20.0, 20.0)
    return found


def walking(now: float) -> tuple[int, int]:
    """Left and right in turn, half a second each, 1-4 s."""
    return ((1 if (now // 500) % 2 == 0 else -1), 0) if 1000.0 <= now < 4000.0 else (0, 0)


def outage(link: Any, start: float, end: float) -> None:
    """The link carries nothing sent in [start, end) until it is back: then all of it, a retransmission later, in
    order (TCP over a burst of losses)."""
    original = link.arrival

    def arrival(sent: float) -> float:
        t = original(sent)
        if start <= sent < end:
            t = max(t, end + link.one_way_ms + RTO_MS)
            link.last = max(link.last, t)
        return t

    link.arrival = arrival


def play(profile: tuple[float, float, float], seed: int, held: Held, until: float = 6500.0, presses: list[float] = (),
         stall: tuple[float, float] | None = None, cut: tuple[float, float] | None = None) -> dict[str, Any]:
    """A predicting window in the co-op room (open floor; the bandit beside it when attacking) over the probe's link:
    keys as ``held`` says, Space at ``presses`` (Feedback.press, its tick sent with the attack, as the arena does).
    ``stall``: (start, end) ms with no server tick (its event loop blocked; the ticks missed are skipped, as
    Server._run_clock does). ``cut``: (start, end) ms in which the link carries nothing either way (a loss burst).
    Records each tick's body, ``ack`` and direction, and what was sent."""
    rtt, jitter, loss = profile
    queued: list[int] = []
    swings: list[float] = []
    ticks: list[tuple[float, float, int, int, int, int]] = []  # (x, y, ack, held, dx, dy) after each tick
    sent: dict[int, tuple[int, int]] = {}

    def intent(t: float, _shown: list[Any]) -> tuple[Any, ...]:
        return (*held(t), "attack", queued.pop(0)) if queued else (*held(t), None)

    def frame(t: float, s: Session) -> None:
        for _ in [p for p in presses if t - FRAME_MS < p <= t]:
            tick = s.feedback.press(t / 1000)
            if tick is not None:
                queued.append(tick)
                swings.append(t)

    with coop_room() as room:
        room.enemies[BANDIT].state = TargetState(hp=100_000.0, max_hp=100_000.0)
        step, s = room.step, None

        def stepped() -> None:
            if stall is None or not stall[0] <= s.now < stall[1]:
                step()
            p = room.players[s.eid]
            ticks.append((p.body.center_x, p.body.center_y, p.ack, p.held, p.dx, p.dy))

        room.step = stepped  # type: ignore[method-assign]
        start = (568.0, 256.0) if presses else OPEN
        s = Session(room, rtt, jitter, loss, seed, intent=intent, frame=frame, held=held,
                    setup=lambda room, eid: place(room, eid, *start, 0))
        if cut is not None:
            outage(s.up, *cut)
            outage(s.down, *cut)
        send_input = wire.input_frame

        def recorded(entity: int, seq: int, dx: int, dy: int, *rest: Any, **extra: Any) -> wire.Message:
            sent[seq] = (dx, dy)
            return send_input(entity, seq, dx, dy, *rest, **extra)

        wire.input_frame = recorded  # type: ignore[assignment]
        try:
            s.run(until)
        finally:
            wire.input_frame = send_input  # type: ignore[assignment]
        own = next(r for r in s.latest["players"] if r[0] == s.eid)
        return {"ticks": ticks, "sent": sent, "step": room.step_px, "swings": swings, "own": own,
                "shown": s.own_shown, "body": s.prediction.body, "unread": list(s.prediction.inputs),
                "attacks": room.players[s.eid].attack_seq, "stale": room.stale_attacks,
                "refused": room.refused_attacks, "cooldown": room.cooldown,
                "corrections": [px for _, px, _, _ in s.corrections]}


def check(got: dict[str, Any], quiet_from: float = 5000.0) -> None:
    """Every tick: at most one step; a step only in a direction an input gave, read that tick or walked on within HOLD
    of the last read, and in its sense. At the end (keys let go, the link quiet): the server still, the window's avatar
    exactly on the server's row, with nothing unread but inputs that walk nowhere."""
    step, sent, ticks = got["step"], got["sent"], got["ticks"]
    for before, after in zip(ticks, ticks[1:]):
        mx, my = after[0] - before[0], after[1] - before[1]
        assert math.hypot(mx, my) <= step + 1e-6, f"more than one step in a tick: {math.hypot(mx, my):.3f} px"
        if math.hypot(mx, my) <= 1e-9:
            continue
        x, y, ack, held, dx, dy = after
        assert (dx or dy) and held < HOLD, "a step with no direction to walk"
        if ack != before[2]:
            assert held == 0 and sent[ack] == (dx, dy), "the direction of the input read that tick"
        else:
            assert 1 <= held < HOLD, "nothing read: the last direction, within HOLD"
        assert mx * dx >= -1e-9 and my * dy >= -1e-9 and (dx or abs(mx) <= 1e-9) and (dy or abs(my) <= 1e-9)
    tail = ticks[-int((6500.0 - quiet_from) / 1000 * wire.HZ):]
    assert len({(t[0], t[1]) for t in tail}) == 1, "the server stopped once the keys were let go"
    own, shown = got["own"], got["shown"]
    assert shown == (own[1], own[2], own[4], own[5]), "the window ends exactly where the server has it"
    assert all((dx, dy) == (0, 0) for _, dx, dy in got["unread"])


SAFE_PROFILES = (PROFILES[0], PROFILES[3], PROFILES[4], JITTER_ONLY)


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("profile", SAFE_PROFILES, ids=lambda p: f"rtt{p[0]}-jitter{p[1]}-loss{p[2]}")
def test_quick_direction_reversals(seed: int, profile: tuple[float, float, float]) -> None:
    check(play(profile, seed, reversals(seed)))


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("profile", SAFE_PROFILES, ids=lambda p: f"rtt{p[0]}-jitter{p[1]}-loss{p[2]}")
def test_key_release_and_short_taps_leave_no_drift(seed: int, profile: tuple[float, float, float]) -> None:
    check(play(profile, seed, holds))


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("profile", SAFE_PROFILES, ids=lambda p: f"rtt{p[0]}-jitter{p[1]}-loss{p[2]}")
def test_attacks_mashed_while_walking_never_start_twice(seed: int, profile: tuple[float, float, float]) -> None:
    """Space mashed (about every 70 ms) while walking left and right: every swing shown is one attack the server
    starts (or, beyond OD1's envelope, drops stale and counts), none twice, none refused in the cooldown; and the walk
    stays the inputs' own."""
    got = play(profile, seed, walking, presses=mash(seed))
    check(got)
    assert got["refused"] == 0, "no swing shown is refused in the cooldown"
    if profile[0] <= 100:
        assert got["stale"] == 0
    assert got["attacks"] + got["stale"] == len(got["swings"]), "each swing shown: one attack, or one stale"
    tick_ms = 1000 / wire.HZ
    assert all(b - a >= got["cooldown"] * tick_ms - tick_ms - FRAME_MS for a, b in zip(got["swings"], got["swings"][1:]))


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("profile", (PROFILES[0], PROFILES[3], PROFILES[4]), ids=lambda p: f"rtt{p[0]}-jitter{p[1]}-loss{p[2]}")
@pytest.mark.parametrize("trouble", ["loss burst 300 ms", "server stall 1200 ms", "outage 1500 ms"])
def test_loss_bursts_stalls_and_outages(trouble: str, seed: int, profile: tuple[float, float, float]) -> None:
    """While walking and reversing (reversals) and around a release (holds): a burst of losses during a hold, a server
    stall of more than a second (its ticks skipped after), an outage of 1.5 s both ways. The queue overflows (the
    newest directions kept) or empties (the last walked on within HOLD); never more than one step a tick, nothing
    walked that no input gave, the server stops after the keys are let go, and the window ends on its row."""
    window = {"loss burst 300 ms": {"cut": (1200.0, 1500.0)}, "server stall 1200 ms": {"stall": (1100.0, 2300.0)},
              "outage 1500 ms": {"cut": (1100.0, 2600.0)}}[trouble]
    check(play(profile, seed, holds, **window))
    check(play(profile, seed, reversals(seed), **window))


def test_with_no_loss_the_prediction_is_exact() -> None:
    """With no loss and nothing changing (OD11: one input, one step): no correction at all, on every seed, through
    reversals, holds and short taps."""
    for seed in SEEDS:
        for held in (reversals(seed), holds):
            got = play(PROFILES[0], seed, held)
            assert max(got["corrections"]) <= CORRECTED, seed


# --- Feedback's reckoning (M4-2 review follow-up) -------------------------------------------------------------


def state(tick: int) -> wire.Message:
    return {"tick": tick, "players": [], "enemies": []}


def test_the_reckoning_rides_out_a_retransmission_but_follows_a_stall() -> None:
    """Snapshots a tick apart, each 20 ms on the way (0.4 tick: lateness under a tick never counts). A ~400 ms TCP
    retransmission hold (8 snapshots arriving together late) leaves the reckoning where it was; a server stall of a
    second (its tick 20 behind from then on) brings it down after RECKONING snapshots in a row, not before."""
    feedback = Feedback()
    feedback.baseline(state(100), 10, 5.0)  # tick 100 seen at 5.0 s

    def arrive(k: int, at: float) -> None:
        feedback.update(state(100 + k), 1, at)

    for k in range(1, 30):
        arrive(k, 5.0 + k / wire.HZ + 0.02)
    assert feedback.tick(7.0) == 140, "lateness under a tick: kept"
    for k in range(30, 38):  # held back 400 ms by a lost segment, then all at once
        arrive(k, 5.0 + 38 / wire.HZ + 0.02)
    for k in range(38, 60):
        arrive(k, 5.0 + k / wire.HZ + 0.02)
    assert feedback.tick(8.0) == 160, "a retransmission hold: kept"
    late = wire.HZ  # (RECKONING: a second's worth of snapshots, pinned here by value)
    for k in range(60, 60 + late - 1):  # the server stalled a second: its tick 20 behind from here on
        arrive(k - 20, 5.0 + k / wire.HZ + 0.02)
    assert feedback.tick(9.0) == 180, "not yet"
    arrive(60 + late - 1 - 20, 5.0 + (60 + late - 1) / wire.HZ + 0.02)
    assert feedback.tick(9.0) == 159, "RECKONING late in a row: it follows the stall"


# --- the one step ------------------------------------------------------------------------------------------------


def test_the_prediction_walks_through_the_authoritys_own_step(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both sides call SceneRoom.walk: the authority's tick (each player's step) and the prediction (each input built
    and each replay). No other code in mesh_net moves a body (the source scan: tests/test_hd2d_net_parity.py)."""
    calls: list[str] = []
    original = SceneRoom.walk

    def spy(self: SceneRoom, body: Any, dx: int, dy: int, solids: list[Any]) -> None:
        calls.append("walk")
        original(self, body, dx, dy, solids)

    monkeypatch.setattr(SceneRoom, "walk", spy)
    with coop_room() as room:
        eid = room.join()
        place(room, eid, *OPEN, 0)
        send(room, eid, 1, 1, 0)
        room.step()
        assert calls == ["walk"], "the authority"
        prediction = Prediction()
        prediction.start(room, room.snapshot(), eid)
        prediction.next((1, 0))
        prediction.sent(2)
        assert calls == ["walk", "walk"], "an input built"
        prediction.reconcile(room.snapshot(), eid)
        assert calls == ["walk", "walk", "walk"], "its replay"
