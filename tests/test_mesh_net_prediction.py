"""M4-3: the server reads one input a tick (owner decision OD11) and a window predicts its own avatar (OD3).

- The queue (mesh_net.scene_room.SceneRoom.input and step): one input read a tick, the oldest; at most DEPTH waiting, a
  full queue dropping its oldest direction but never an attack, a use or a take (they run when a later input is read);
  ``ack`` is the input the tick read; with nothing waiting nothing is walked (HOLD 1); a standing player's older still
  inputs are dropped. An input's actions run from where the player stood before its step: where the window showed it.
- The prediction (mesh_net.scene_room.Prediction): each input walks the avatar at once through SceneRoom.walk (one
  step for both sides: tests/test_hd2d_net_parity.py); each snapshot puts it back on the server's row and walks again
  what the server has not read; elevation and floor take the server's at once, x/y fades; nothing hidden is carried.
  Started anew at a welcome (a resume's too) and when a room shows; stopped at an enter and at a session's end.
- The owner's safeguards, on the probe's virtual clock and TCP link model (tooling/m4_latency_probe.py), seeds 7, 8 and 9:
  quick direction reversals, key release and short taps, attacks mashed while walking, the cooldown, jitter, loss
  bursts, a server stall of more than a second and a network outage of 1.5 s. Every tick the server walks at most one
  step, only a direction an input gave (read that tick: HOLD 1), its way; it stops once the keys are
  let go; no attack starts twice or without a swing shown; and the window ends exactly where the server has it.
- Feedback's reckoning rides out a TCP retransmission hold and follows a real server stall (M4-2 review follow-up).
"""

from __future__ import annotations

import asyncio
import copy
import math
import random
from collections import deque
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
    """DEPTH (8) waiting and more come (a burst after a stall): the oldest directions are dropped (counted), never their
    actions: an attack and a use carried by dropped inputs run on the tick that reads a later input. Never more than one
    step a tick."""
    with coop_room() as room:
        eid = room.join()
        place(room, eid, 568.0, 256.0, 0)  # (next to the bandit, facing it)
        p, step = room.players[eid], room.step_px
        room.enemies[BANDIT].state = TargetState(hp=100.0, max_hp=100.0)
        burst = [(1, 0, -1, "attack"), (2, 0, -1, "use"), (3, 0, 1, None), (4, 0, 0, None)]
        burst += [(seq, 0, 1, None) for seq in range(5, 12)]
        for seq, dx, dy, action in burst:
            send(room, eid, seq, dx, dy, action)
        assert DEPTH == 8 and [m[0] for m in p.moves] == list(range(4, 12)), "the newest eight wait"
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
    """One input and nothing after it: walked on its own tick only (HOLD 1: never a step no input gave), then the body
    stops; ``ack`` stays the input read."""
    with coop_room() as room:
        eid = room.join()
        place(room, eid, *OPEN, 0)
        send(room, eid, 1, 1, 0)
        xs = []
        for _ in range(HOLD + 3):
            room.step()
            xs.append(at(room, eid)[0])
        assert HOLD == 1 and xs == [OPEN[0] + room.step_px * min(i, HOLD) for i in range(1, HOLD + 4)]
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
        room._attack = lambda p, view=None: (made.append(p.body.center_x), attack(p, view))[1]  # type: ignore[method-assign]
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
    assert arena.outgoing() == ((0, 0), None, 105, None)
    arena.act("attack", 103, 101.25)
    arena.press(keys.RIGHT, 0)
    assert arena.outgoing() == ((1, 0), "attack", 103, 101.25), "an attack's view tick rides with it (M4-5)"


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

        def sync(self, state: Any, positions: dict[int, Any], own: Any, dt: float, enemies: Any = None) -> None:
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
    arena.seq, arena.riders = 3, 0  # (and an action pressed after a press-built input, waiting for the next)
    WorldArena.on_frame(arena, enter, 1.0)
    assert arena.prediction.body is None and not arena.prediction.inputs, "stopped at the enter"
    assert arena.riders is None, "no action held back for an input of the last room"
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
            arena.riders = 0
            if make == "scene":
                asyncio.run(Arena.session(arena, port))
            else:
                arena.__dict__.update(port=None, character=None, note=lambda _e: None, phase="playing", room="start:1",
                                      pending=None, requests=[])
                asyncio.run(WorldArena.session(arena, port))
            assert arena.prediction.body is None and not arena.prediction.inputs and arena.riders is None, make


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


# --- gaps the review of #613 found ---------------------------------------------------------------------------


def test_an_action_waits_for_its_own_input_behind_a_step() -> None:
    """Two inputs read in turn, the second carrying the attack (and then a take): neither runs on the tick that
    reads the first, a step early; each runs on the tick that reads its own input, from where the first left it."""
    with coop_room() as room:
        eid = room.join()
        place(room, eid, *OPEN, 0)
        p, step = room.players[eid], room.step_px
        made: list[float] = []
        attack = room._attack
        room._attack = lambda pl, view=None: (made.append(pl.body.center_x), attack(pl, view))[1]  # type: ignore[method-assign]
        send(room, eid, 1, 1, 0)
        send(room, eid, 2, 1, 0, "attack")
        room.step()
        assert made == [] and p.attack_seq == 0, "not with the first input's step"
        room.step()
        assert made == [OPEN[0] + step] and p.attack_seq == 1
        send(room, eid, 3, 1, 0)
        send(room, eid, 4, 1, 0, "take")
        room.step()
        assert p.actions == [(4, "take")], "the take waits for its own input too"
        room.step()
        assert p.actions == []


def two_rooms() -> tuple[SceneRoom, SceneRoom]:
    with coop_room() as server, coop_room() as client:  # (coop_room opens the gate: the client's copy is locked again)
        client.locked = {i for i, (_, c) in client.doors.items() if c.get("starts_locked", True)}
        return server, client


def test_the_prediction_walks_through_what_the_snapshot_opened() -> None:
    """The window's copy of the room never steps, so its own gate stays locked; the server's is open. Predicting
    through the snapshot's account of what blocks (its open gates, its live enemies), the window walks through the
    gate with the server, never a correction."""
    server, client = two_rooms()
    gate = next(iter(client.doors))
    assert gate in client.locked and gate not in server.locked
    server.drain = 0  # (what blocks is the question here: the backlog below is kept whole, as "deep" keeps it)
    eid = server.join()
    place(server, eid, 380.0, 256.0, 0)  # (a locked gate stops a walk right at 390.5)
    prediction = Prediction()
    prediction.start(client, server.snapshot(), eid)
    for seq in range(1, DEPTH + 1):  # (sent at once: each snapshot below leaves some unread, walked again)
        prediction.next((1, 0))
        prediction.sent(seq)
        send(server, eid, seq, 1, 0)
    moved = []
    for _ in range(DEPTH):
        server.step()
        moved.append(prediction.reconcile(server.snapshot(), eid)[0])
    assert max(moved) <= CORRECTED and prediction.body is not None and prediction.body.center_x > 432.0


def test_a_correction_never_moves_the_avatar_where_it_is_shown() -> None:
    """A second correction while the first still fades: the avatar is drawn exactly where it was the frame before
    (the new offset carries the old one's remainder), and both fade out together."""
    with coop_room() as room:
        eid = room.join()
        place(room, eid, *OPEN, 0)
        prediction = Prediction()
        prediction.start(room, room.snapshot(), eid)
        for seq in (1, 2, 3, 4):
            prediction.next((1, 0))
            prediction.sent(seq)
        room.players[eid].ack = 2  # (input 2 dropped: one step fewer)
        prediction.reconcile(room.snapshot(), eid)
        before = prediction.shown(SMOOTH_S / 2)[0]
        room.players[eid].ack = 4  # (input 4 dropped too)
        prediction.reconcile(room.snapshot(), eid)
        assert prediction.shown(0.0)[0] == pytest.approx(before), "no jump where it is drawn"
        assert prediction.shown(SMOOTH_S)[0] == OPEN[0], "and all of it gone after SMOOTH_S"


def test_a_take_or_use_is_chosen_where_the_window_shows_itself() -> None:
    """E near a drop the predicted avatar stands by (the server's row is still far from it): a take, in both arenas,
    since the server runs it from where the window shows the player."""
    with coop_room() as room:
        eid = room.join()
        place(room, eid, *OPEN, 0)
        state = room.snapshot()
        far = next(r for r in state["players"] if r[0] == eid)
        view = SimpleNamespace(near_drop=lambda x, y, _state: x > 400.0, swing=lambda *_a: None)
        for make in ("scene", "world"):
            prediction = Prediction()
            prediction.start(room, state, eid)
            assert prediction.body is not None
            prediction.body.center_x = 450.0  # (walked there, the server not yet)
            keys = SimpleNamespace(SPACE=32, E=101, P=1, I=2, Y=3, N=4, L=5, ESCAPE=6, F2=7, R=8)
            arena: Any = SimpleNamespace(actions=[], action_keys=set(), directions={}, keys=[], prediction=prediction,
                                         arcade=SimpleNamespace(key=keys), view=view, feedback=Feedback())
            arena.act = lambda action, tick=None, view=None, a=arena: Arena.act(a, action, tick, view)
            if make == "scene":
                arena.client = SimpleNamespace(entity=eid, state=state)
                SceneArena.press(arena, keys.E, 0)
            else:
                arena.__dict__.update(phase="playing", shown="start:1", room="start:1", entity=eid, state=state,
                                      connected=True, note=lambda _e: None, request=None, _own=lambda: far)
                WorldArena.press(arena, keys.E, 0)
            assert arena.actions == [("take", None, None)], make


def test_space_after_a_press_built_input_swings_where_the_server_runs_it() -> None:
    """A direction pressed (its input built: the avatar steps at once) and Space before that input goes: the swing
    showed from after that step, so the attack waits for the next input, which the server reads from there. The
    window and the server agree on where the attack is made."""
    keys = SimpleNamespace(**{n: i for i, n in enumerate("W UP S DOWN A LEFT D RIGHT SPACE E ESCAPE F2 R N".split())})
    with coop_room() as room:
        eid = room.join()
        place(room, eid, *OPEN, 0)
        arena: Any = Arena(SimpleNamespace(push_handlers=lambda **_kw: None), SimpleNamespace(key=keys))
        arena.prediction, arena.feedback = Prediction(), Feedback()
        arena.feedback.baseline(room.snapshot(), room.cooldown, 0.0)
        arena.prediction.start(room, room.snapshot(), eid)
        arena.clock = lambda: 0.0
        arena.press(keys.RIGHT, 0)
        shown = arena.prediction.body.center_x
        arena.act("attack", arena.feedback.press(0.0))  # (SceneArena.press: Space, the same frame)
        made: list[float] = []
        attack = room._attack
        room._attack = lambda pl, view=None: (made.append(pl.body.center_x), attack(pl, view))[1]  # type: ignore[method-assign]
        for seq in (1, 2):
            direction, action, tick, view = arena.outgoing()
            assert (action is None) == (seq == 1), "the built input goes without it; the next carries it"
            arena.prediction.sent(seq)
            room.input(eid, wire.input_frame(eid, seq, *direction, tick, action, view))
            room.step()
        assert made == [shown] == [OPEN[0] + room.step_px]


class Labels:
    """Each seq a window gave its prediction (``Prediction.sent``), and the seqs (with directions) the server read."""

    def __init__(self, prediction: Prediction) -> None:
        self.given: list[int] = []
        self.got: list[int] = []
        sent = prediction.sent
        prediction.sent = lambda seq: (self.given.append(seq), sent(seq))[1]  # type: ignore[method-assign]


def test_an_n6_window_labels_each_input_with_the_seq_it_goes_as() -> None:
    """A scene window over a real server and socket, a key held: every input it predicts is labelled with the seq
    the server receives it as (the acks it reconciles by mean those inputs)."""
    from mesh_net.scene_room import check_progress, check_state, parse_input
    from mesh_net.server import Server

    keys = SimpleNamespace(**{n: i for i, n in enumerate("W UP S DOWN A LEFT D RIGHT SPACE E ESCAPE F2 R N".split())})

    async def run() -> Labels:
        with coop_room() as room:
            server = Server(room)
            port = await server.start(0)

            class Window(Arena):
                def on_state(self, state: wire.Message, entity: int, fresh: bool) -> None:
                    if fresh:
                        self.feedback.baseline(state, room.cooldown, self.clock())
                        self.prediction.start(room, state, entity)
                    else:
                        self.prediction.reconcile(state, entity)

                def describe(self, state: wire.Message, entity: int) -> str:
                    return ""

            window = Window(SimpleNamespace(push_handlers=lambda **_kw: None), SimpleNamespace(key=keys))
            window.prediction, window.feedback = Prediction(), Feedback()
            window.checks = {"check": lambda m: check_state(m, room.identity, room), "check_input": parse_input,
                             "progress": check_progress}
            labels = Labels(window.prediction)
            received = room.input
            room.input = lambda e, m: (labels.got.append(m["seq"]), received(e, m))[1]  # type: ignore[method-assign]
            window.keys = [keys.RIGHT]
            try:
                await asyncio.wait_for(window.session(port), 0.8)
            except TimeoutError:
                pass
            finally:
                await server.close()
            return labels

    labels = asyncio.run(run())
    assert len(labels.got) >= 5 and labels.given[:len(labels.got)] == labels.got


def test_an_n7_window_labels_each_input_with_the_seq_it_goes_as() -> None:
    """The world window over a real world server and socket, once its room shows, a key held: every input it
    predicts is labelled with the seq the server receives it as."""
    from mesh_net.scene_room import disposable_project
    from mesh_net.server import WorldServer
    from mesh_net.world import World, expedition_files

    keys = SimpleNamespace(**{n: i for i, n in enumerate("W UP S DOWN A LEFT D RIGHT SPACE E ESCAPE F2 R N".split())})

    async def run() -> Labels:
        with disposable_project(expedition_files(), scaffold=False) as root:
            world = World(root)
        server = WorldServer(world)
        port = await server.start(0)
        window: Any = WorldArena.__new__(WorldArena)
        with disposable_project(expedition_files(), scaffold=False) as root:
            WorldArena.__init__(window, SimpleNamespace(push_handlers=lambda **_kw: None), SimpleNamespace(key=keys),
                                root, "")
        labels = Labels(window.prediction)
        received = world.input
        world.input = lambda pid, m: (labels.got.append(m["seq"]), received(pid, m))[1]  # type: ignore[method-assign]

        async def show() -> None:  # (WorldArena.draw, without a window: the room shows once entered)
            while window.pending is None:
                await asyncio.sleep(0.01)
            window.shown, window.pending, window.phase = window.room, None, "playing"
            window.prediction.start(window.defs[window.key].proto, window.state, window.entity)
            window.keys = [keys.RIGHT]

        shower = asyncio.create_task(show())
        try:
            await asyncio.wait_for(window.session(port), 1.0)
        except TimeoutError:
            pass
        finally:
            shower.cancel()
            await server.close()
        return labels

    labels = asyncio.run(run())
    assert len(labels.got) >= 5 and labels.given[:len(labels.got)] == labels.got


# --- the queue's settings (M4-3 round 3: the owner chooses at the M4 checkpoint) -----------------------------


def test_the_queue_settings_are_checked_and_bounded() -> None:
    """depth 1-20, hold 1-5, drain 0 (off) or 2-20, whole numbers only: anything else is refused, before a room is
    built. The defaults are the provisional preset, "drain" (owner decision 2026-11-24); "deep" and "small" are the
    others, and a knob given overrides its preset's."""
    from mesh_net.scene_room import DRAIN, QUEUE, QUEUE_LIMITS, QUEUE_PRESETS, queue_settings

    assert QUEUE == "drain" and queue_settings() == (DEPTH, HOLD, DRAIN) == (8, 1, 4)
    assert QUEUE_PRESETS == {"drain": (8, 1, 4), "deep": (8, 1, 0), "small": (2, 5, 0)}
    assert queue_settings(preset="small") == (2, 5, 0) and queue_settings(preset="deep") == (8, 1, 0)
    assert queue_settings(drain=0, preset="drain") == (8, 1, 0) and queue_settings(depth=4, preset="small") == (4, 5, 0)
    for bad in ("fast", "", 3, "DRAIN"):
        with pytest.raises(ValueError, match="preset"):
            queue_settings(preset=bad)
    assert QUEUE_LIMITS == {"depth": (1, 20), "hold": (1, wire.HZ // 4), "drain": (2, 20)}
    for good in ((1, 1, 0), (20, 5, 20), (2, 5, 2), (8, 1, 4)):
        assert queue_settings(*good) == good
    for bad in ({"depth": 0}, {"depth": 21}, {"depth": -1}, {"depth": True}, {"depth": 2.0}, {"depth": "8"},
                {"hold": 0}, {"hold": 6}, {"drain": 1}, {"drain": 21}, {"drain": -4}, {"drain": False}):
        with pytest.raises(ValueError, match="input queue"):
            queue_settings(**bad)
    from mesh_net.scene_room import COOP_SCENE, coop_files, disposable_project

    with disposable_project(coop_files(), scaffold=False) as root:
        with pytest.raises(ValueError, match="depth"):
            SceneRoom(root / COOP_SCENE, root, depth=0)
        room = SceneRoom(root / COOP_SCENE, root, depth=2, hold=5, drain=4)
    assert (room.depth, room.hold, room.drain) == (2, 5, 4)


def test_the_servers_take_the_queue_settings_from_flags_or_the_environment() -> None:
    """mesh_net.server: each setting from its flag, else MESH_NET_INPUT_<NAME>, else the default, checked; a world's
    rooms (and every instance made from them) take them; the server refuses a bad one at start, saying why."""
    import argparse
    import subprocess
    import sys

    from mesh_net.server import queue_from

    none = argparse.Namespace(queue=None, input_depth=None, input_hold=None, input_drain=None)
    assert queue_from(none, {}) == {"depth": 8, "hold": 1, "drain": 4}, "the provisional default: drain"
    assert queue_from(none, {"MESH_NET_QUEUE": "small"}) == {"depth": 2, "hold": 5, "drain": 0}
    deep = argparse.Namespace(queue="deep", input_depth=None, input_hold=None, input_drain=None)
    assert queue_from(deep, {"MESH_NET_QUEUE": "small"}) == {"depth": 8, "hold": 1, "drain": 0}, "the flag first"
    env = {"MESH_NET_INPUT_DEPTH": "2", "MESH_NET_INPUT_HOLD": "5", "MESH_NET_INPUT_DRAIN": "4"}
    assert queue_from(none, env) == {"depth": 2, "hold": 5, "drain": 4}
    flags = argparse.Namespace(queue=None, input_depth=6, input_hold=None, input_drain=0)
    assert queue_from(flags, env) == {"depth": 6, "hold": 5, "drain": 0}, "a flag beats the environment"
    for bad in ({"MESH_NET_INPUT_DEPTH": "x"}, {"MESH_NET_INPUT_DRAIN": "1"}, {"MESH_NET_INPUT_HOLD": "9"},
                {"MESH_NET_QUEUE": "fast"}):
        with pytest.raises(ValueError):
            queue_from(none, bad)
    from mesh_net.scene_room import disposable_project
    from mesh_net.world import World, expedition_files

    with disposable_project(expedition_files(), scaffold=False) as root:
        world = World(root, depth=2, hold=5, drain=4)
    inst = world._create(next(k for k, d in world.defs.items() if d.expedition), 1)
    for room in [d.proto for d in world.defs.values()] + [world.hub.room, inst.room]:
        assert (room.depth, room.hold, room.drain) == (2, 5, 4)
    done = subprocess.run([sys.executable, "-m", "mesh_net.server", "--coop", "--input-depth", "0"], cwd=REPO,
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 2 and "input queue depth" in done.stderr


def test_the_drain_shortens_a_lasting_backlog_one_direction_at_a_time_never_an_action() -> None:
    """drain 4: a player walking with more than one input waiting after each read for 4 ticks in a row loses the
    oldest waiting direction (counted; one step), never its action, and never walks two steps a tick. Off (0): the
    backlog lasts."""
    from mesh_net.scene_room import COOP_SCENE, coop_files, disposable_project

    for drain in (4, 0):
        with disposable_project(coop_files(), scaffold=False) as root:
            room = SceneRoom(root / COOP_SCENE, root, drain=drain)
        eid = room.join()
        place(room, eid, 150.0, 200.0, 0)
        for seq in range(1, 5):  # (a burst: four waiting)
            send(room, eid, seq, 1, 0, "use" if seq == 2 else None)
        seq, xs, drops, after_4 = 4, [at(room, eid)[0]], [], []
        p = room.players[eid]
        for tick in range(1, 13):  # (one more each tick, as a window sends: the backlog would stay)
            seq += 1
            send(room, eid, seq, 1, 0)
            before = room.drained_moves
            room.step()
            xs.append(at(room, eid)[0])
            drops += [tick] * (room.drained_moves - before)
            if tick == 4:
                after_4 = [m[0] for m in p.moves]
        assert all(0 <= b - a <= room.step_px + 1e-9 for a, b in zip(xs, xs[1:])), "never two steps a tick"
        assert p.actions == [], "the use ran"
        if drain:  # (four reads in a row with more than one waiting, each time: ticks 4, 8 and 12)
            assert drops == [4, 8, 12] and room.dropped_moves == 0 and len(p.moves) == 1, "one at a time, 4 ticks apart"
            assert after_4 == [6, 7, 8], "the oldest waiting (input 5) went, never a newer one"
        else:
            assert room.drained_moves == room.dropped_moves == 0 and len(p.moves) == 4, "off: the backlog lasts"


def queue_room(arena: str, depth: int, hold: int, drain: int) -> tuple[Callable[..., None], Callable[[], None], Any, Any]:
    """A player in a room built with these queue settings, ready to walk east a few steps: (send(seq, dx, dy), step(),
    the room, the player). "n6": the co-op room; "n6 stairs": the floors demo's stairs, on them; "n7": a world's hub
    instance, through World.input and World.step."""
    from mesh_net.scene_room import COOP_SCENE, coop_files, disposable_project
    from mesh_net.world import World, expedition_files

    if arena == "n7":
        with disposable_project(expedition_files(), scaffold=False) as root:
            d = Driver(World(root, depth=depth, hold=hold, drain=drain))
        a, _ = d.join()
        inst, eid = d.room(a), d.m(a).eid

        def n7_send(seq: int, dx: int, dy: int) -> None:
            d.w.input(a, wire.input_frame(eid, seq, dx, dy, inst.room.tick, room=d.m(a).instance))

        return n7_send, d.step, inst.room, d.player(a)
    if arena == "n6 stairs":
        with stairs_room() as room:
            pass
        room.depth, room.hold, room.drain = depth, hold, drain  # (as SceneRoom(..., depth=, hold=, drain=) sets them)
        eid = room.join()
        to_stairs_edge(room, eid)
    else:
        with disposable_project(coop_files(), scaffold=False) as root:
            room = SceneRoom(root / COOP_SCENE, root, depth=depth, hold=hold, drain=drain)
        eid = room.join()
        place(room, eid, *OPEN, 0)
    return lambda seq, dx, dy: send(room, eid, seq, dx, dy), room.step, room, room.players[eid]


@pytest.mark.parametrize("arena", ["n6", "n6 stairs", "n7"])
@pytest.mark.parametrize("preset", ["small", "deep", (5, 3, 0)], ids=str)
def test_every_room_queues_with_its_own_depth_and_hold(arena: str, preset: Any) -> None:
    """A room built with a preset (or raw settings) keeps at most its own depth waiting (the newest; the rest counted
    as dropped) and walks the last direction read for its own hold, never the module's defaults: N6, on stairs (no
    slope rule touches a full queue or the hold), and an N7 instance."""
    from mesh_net.scene_room import queue_settings

    depth, hold, drain = queue_settings(*(preset if isinstance(preset, tuple) else ()),
                                        preset=preset if isinstance(preset, str) else None)
    send_input, step, room, p = queue_room(arena, depth, hold, drain)
    assert (room.depth, room.hold, room.drain) == (depth, hold, drain)
    for seq in range(1, depth + 4):  # (a burst of still inputs: three more than the room keeps)
        send_input(seq, 0, 0)
    assert [m[0] for m in p.moves] == list(range(4, depth + 4)) and room.dropped_moves == 3, "its own depth"
    step()
    assert not p.moves and p.ack == depth + 3
    start, step_px = (p.body.center_x, p.body.center_y), room.step_px
    send_input(depth + 4, *((0, 1) if arena == "n6 stairs" else (1, 0)))  # (up the stairs; else east)
    walked = []
    for _ in range(hold + 2):
        step()
        walked.append(round(math.dist(start, (p.body.center_x, p.body.center_y)) / step_px, 1))
    assert walked == [float(min(i, hold)) for i in range(1, hold + 3)], "walked on for its own hold, then stopped"


def test_ordinary_walking_never_drains() -> None:
    """A window walking on a steady link: one input waits after each read (the next one is already in). That is no
    backlog: the drain never drops a step, and every input is walked on its own tick."""
    with coop_room() as room:
        eid = room.join()
        place(room, eid, *OPEN, 0)
        p, xs = room.players[eid], []
        send(room, eid, 1, 1, 0)
        for seq in range(2, 42):  # (left and right in turn: in place, a step each tick)
            send(room, eid, seq, 1 if seq % 2 else -1, 0)
            room.step()
            assert p.ack == seq - 1 and len(p.moves) == 1
            xs.append(at(room, eid)[0])
        assert room.drain == 4 and room.drained_moves == room.dropped_moves == 0
        assert xs == [OPEN[0] + room.step_px * (i % 2 == 0) for i in range(len(xs))]


def test_leaving_resets_the_drain_count() -> None:
    """A player that leaves (a transfer, a disconnect) with a backlog three ticks old comes back counting from 0: its
    next backlog drains on its 4th tick, not its 1st."""
    with coop_room() as room:
        eid = room.join()
        place(room, eid, *OPEN, 0)
        p, seq = room.players[eid], 0

        def backlog(ticks: int) -> list[int]:
            nonlocal seq
            for _ in range(3):
                seq += 1
                send(room, eid, seq, 0, 1 if seq % 2 else -1)
            drained = []
            for tick in range(1, ticks + 1):
                seq += 1
                send(room, eid, seq, 0, 1 if seq % 2 else -1)
                before = room.drained_moves
                room.step()
                drained += [tick] * (room.drained_moves - before)
            return drained

        assert backlog(room.drain - 1) == [] and p.deep == room.drain - 1
        eid = room.join(room.leave(eid))
        seq = 0
        assert backlog(room.drain) == [room.drain], "counted from 0 again"


@pytest.mark.parametrize("where", ["mid-stairs", "below the landing", "beside the bandit"])
def test_the_drain_never_drops_a_step_at_a_fork(where: str) -> None:
    """Drain preset, a backlog four ticks old whose oldest waiting input is a step that turns the inputs behind it
    (pushes that walk nowhere). Dropping it must leave those inputs within a step of where they lead, on the same
    floor, else the window would replay them down another branch: the drain waits a tick, then drops the next one.
    - mid-stairs (HD-2D): a step north, then pushes east into the stairs' edge, blocked either way: dropped on time;
    - below the landing (HD-2D): the step north is onto the landing (the pushes east blocked on both): another floor;
    - beside the bandit (2D): a step west puts the bandit in the way of the pushes north: they end 3 steps apart."""
    if where == "beside the bandit":
        with coop_room() as room:
            pass
        eid = room.join()
        place(room, eid, 632.0, 244.0, 0)
        plan = [(1, 0), (-1, 0), (1, 0), (-1, 0), (-1, 0)] + [(0, 1)] * 6  # (seqs 1-4 in place; 5: west; then north)
    else:
        with stairs_room() as room:
            pass
        eid = room.join()
        to_stairs_edge(room, eid)
        p, seq = room.players[eid], 0
        while p.body.center_y < (240.0 if where == "mid-stairs" else 288.0):
            seq += 1
            send(room, eid, seq, 1, 1)
            room.step()
        p.seq = p.ack = p.dx = p.dy = 0
        assert p.body.mesh_hd2d_floor == "crossing/col_stairs_west" and p.body.center_x >= 350.0
        plan = [(1, 0)] * 4 + [(0, 1)] + [(1, 0)] * 6  # (seqs 1-4 pushing into the edge; 5: north; then east)
    p = room.players[eid]
    for seq, (dx, dy) in enumerate(plan[:4], 1):
        send(room, eid, seq, dx, dy)
    drops, path = [], []
    for tick, (seq, (dx, dy)) in enumerate(enumerate(plan[4:], 5), 1):
        send(room, eid, seq, dx, dy)
        before = room.drained_moves
        room.step()
        drops += [tick] * (room.drained_moves - before)
        path.append((round(p.body.center_x, 1), round(p.body.center_y, 1), p.body.mesh_hd2d_floor))
    assert room.drain == 4 and room.dropped_moves == 0
    if where == "mid-stairs":
        assert drops[0] == 4, "no fork: dropped on its 4th tick in a row"
    else:
        assert drops[0] == 5, "the turning step kept; the next tick drains"
        assert path[4][2] == ("crossing/col_landing_west" if where == "below the landing" else None), path
        assert where != "beside the bandit" or path[4][:2] == (624.5, 244.0), path


def test_the_fork_check_walks_copies_never_the_real_body() -> None:
    """(#615 review, F02) SceneRoom._forks walks this tick's step and the waiting inputs twice from copies of the body:
    the real body's position, floor and entity data (its elevation, as the floor solver writes it) are untouched,
    here on the stairs, where those walks climb."""
    with stairs_room() as room:
        pass
    eid = room.join()
    to_stairs_edge(room, eid)
    p = room.players[eid]
    p.ack, p.dx, p.dy = 0, 0, 1
    p.moves = deque([(1, 0, 1), (2, 0, 1), (3, -1, 1), (4, 0, 1)])
    data = p.body.mesh_entity_data
    before = (p.body.center_x, p.body.center_y, p.body.mesh_hd2d_floor, copy.deepcopy(data))
    solids = room.solids()
    room._forks(p, solids)
    assert (p.body.center_x, p.body.center_y, p.body.mesh_hd2d_floor, p.body.mesh_entity_data) == before
    assert p.body.mesh_entity_data is data, "its own entity data, not a copy put in its place"
    twin = copy.deepcopy(p.body)
    for _seq, dx, dy in [(0, 0, 1), *p.moves]:
        room.walk(twin, dx, dy, solids)
    assert twin.mesh_entity_data["elevation"] != data["elevation"], "(those walks do climb: the check could tell)"


@pytest.mark.parametrize(("x", "norths", "steps", "forks"), [(636.0, 2, 1.0, False), (632.0, 1, math.sqrt(2), True),
                                                             (632.0, 2, math.sqrt(5), True)])
def test_the_fork_threshold_is_one_step(x: float, norths: int, steps: float, forks: bool) -> None:
    """(#615 review, F05) The drain may cost one step and no more: beside the bandit (2D), the oldest waiting input a
    step west, then ``norths`` steps north. At x 636 the bandit is never in the way: the two ends are exactly one step
    apart, dropped. At 632 the step west puts it in the way of the steps north: the ends are sqrt(2) and sqrt(5) steps
    apart (just over one, about two), refused."""
    with coop_room() as room:
        pass
    eid = room.join()
    place(room, eid, x, 244.0, 0)
    p = room.players[eid]
    p.ack, p.dx, p.dy = 0, 0, 0
    p.moves = deque([(1, -1, 0)] + [(2 + i, 0, 1) for i in range(norths)])
    solids = room.solids()
    ends = []
    for skip in (False, True):
        twin = copy.deepcopy(p.body)
        for i, (_seq, dx, dy) in enumerate([(0, 0, 0), *p.moves]):
            if not (skip and i == 1):
                room.walk(twin, dx, dy, solids)
        ends.append((twin.center_x, twin.center_y))
    assert math.dist(*ends) / room.step_px == pytest.approx(steps)
    assert room._forks(p, solids) is forks


@pytest.mark.parametrize("preset", ["small", "deep", "drain"])
def test_a_full_queue_drops_its_oldest_even_at_a_fork(preset: str) -> None:
    """The fork guard is the drain's alone: a full queue drops its oldest direction whatever it would cost (depth is
    a bound), here a step west beside the bandit that turns the pushes north behind it."""
    from mesh_net.scene_room import COOP_SCENE, coop_files, disposable_project, queue_settings

    depth, hold, drain = queue_settings(preset=preset)
    with disposable_project(coop_files(), scaffold=False) as root:
        room = SceneRoom(root / COOP_SCENE, root, depth=depth, hold=hold, drain=drain)
    eid = room.join()
    place(room, eid, 632.0, 244.0, 0)
    for seq, (dx, dy) in enumerate([(-1, 0)] + [(0, 1)] * depth, 1):
        send(room, eid, seq, dx, dy)
    assert [m[0] for m in room.players[eid].moves] == list(range(2, depth + 2)) and room.dropped_moves == 1


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
