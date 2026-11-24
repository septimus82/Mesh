"""M4-2 combat: the server's hitbox is single-player's (owner decision OD10), and a window shows its own swing at once
and a hit only once the server confirms it (OD4), whatever the latency.

- OD10 parity: single-player's own Combat and Hitbox behaviours, updated at the authority's step (1/HZ s), against
  SceneRoom.step: the same ticks hit, the hitbox stays where it was made, and it hits each target once. (Its level
  is asked as the attacker stands each tick: tests/test_hd2d_same_level.py, on 3D floors.)
- The window's presentation (mesh_net.scene_room.Feedback, through SceneArena's and WorldArena's own handlers) on the
  probe's virtual clock and TCP link model (tooling/m4_latency_probe.py), seeds 7, 8 and 9 at every latency profile:
  the swing within one frame of the press, a flash only after a snapshot confirms the hit, nothing in the cooldown,
  no attack or hit ever duplicated; and its counters taken anew at a welcome (a resume) and at every enter.
"""

from __future__ import annotations

import asyncio
import math
import random
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

import engine.optional_arcade as optional_arcade
from engine.combat_model import TargetState
from engine.physics_model import entity_shape, shapes_overlap
from mesh_net import protocol as wire
from mesh_net.demo import Arena
from mesh_net.scene_client import SceneArena
from mesh_net.scene_room import COOP_SCENE, Feedback, SceneRoom, coop_files, disposable_project, hitbox_ticks
from mesh_net.world import World, expedition_files
from mesh_net.world_client import WorldArena
from tests.test_hd2d_net_parity import sprite
from tests.test_hd2d_same_level import Thing, behaviour
from tooling.m4_latency_probe import BANDIT, FRAME_MS, PROFILES, Session, coop_room, place

pytestmark = pytest.mark.integration  # (rooms built in folders)

SPACE, E = 32, 101
KEYS = SimpleNamespace(SPACE=SPACE, E=E)
FAR = (10_000.0, 10_000.0)


@pytest.fixture(scope="module")
def coop() -> SceneRoom:
    with disposable_project(coop_files(), scaffold=False) as root:
        return SceneRoom(root / COOP_SCENE, root)


# --- OD10: the server's hitbox is single-player's ----------------------------------------------------------------


def single_player_hits(room: SceneRoom, path: list[tuple[tuple[float, float], tuple[float, float]]],
                       monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Combat.attack on the first update, then single-player's Hitbox updated at 1/HZ s: ``path[k]`` is (attacker
    centre, target centre) on update k + 1. The updates (1-based) on which the target took a hit."""
    Combat, Hitbox, Health = behaviour("Combat"), behaviour("Hitbox"), behaviour("Health")
    monkeypatch.setattr(optional_arcade.arcade, "check_for_collision",
                        lambda a, b: shapes_overlap(entity_shape(a), entity_shape(b)))
    enemy_body = room.enemies[BANDIT].body
    actor: Any = sprite(*path[0][0], room._template_size(), {**room.template, "facing": "right"})
    actor.mesh_tag = actor.mesh_name = "player"
    actor.angle, actor.change_x, actor.change_y = 0.0, 0.0, 0.0
    target: Any = Thing(**vars(sprite(*path[0][1], (enemy_body.width, enemy_body.height),
                                      dict(enemy_body.mesh_entity_data))))
    target.mesh_tag, target.mesh_name, target.visible = room.target_tag, "bandit", True
    target.remove_from_sprite_lists = lambda: None
    window = MagicMock()
    window.hd2d_world, window.game_state_controller = None, None
    health = Health(target, window, max_hp=100.0, hp=100.0)
    target.mesh_behaviours_runtime = [health]
    made: list[Any] = []

    def create(data: dict[str, Any]) -> Any:
        made.append(SimpleNamespace(center_x=data["x"], center_y=data["y"], width=room.hitbox, height=room.hitbox,
                                    mesh_entity_data=data, mesh_tag="", remove_from_sprite_lists=lambda: None))
        return made[-1]

    window.scene_controller = SimpleNamespace(_create_sprite=create, add_sprite_to_layer=lambda *_a: None,
                                              all_sprites=[actor, target])
    combat = Combat(actor, window, damage=1.0, range=room.reach, hitbox_size=room.hitbox, cooldown=1.0)
    assert combat.attack()
    (box,) = made
    window.scene_controller.all_sprites.append(box)
    hitbox = Hitbox(box, window, **box.mesh_entity_data["behaviour_config"]["Hitbox"])
    hits, hp = [], health.hp
    for k, (at, to) in enumerate(path, 1):
        actor.center_x, actor.center_y = at
        target.center_x, target.center_y = to
        hitbox.update(1 / wire.HZ)
        if health.hp < hp:
            hits.append(k)
        hp = health.hp
    return hits


def server_hits(room: SceneRoom, path: list[tuple[tuple[float, float], tuple[float, float]]]) -> list[int]:
    """The authority: a player facing right attacks on the first tick; ``path[k]`` is (attacker centre, target centre)
    as tick k + 1 runs (nobody walks: the tool puts them there). The ticks (1-based) on which the target took a hit."""
    eid = room.join()
    enemy = room.enemies[BANDIT]
    saved = (enemy.state, enemy.body.center_x, enemy.body.center_y, enemy.hit_seq)
    enemy.state = TargetState(hp=100.0, max_hp=100.0)
    p = room.players[eid]
    p.facing = 0
    try:
        room.input(eid, wire.input_frame(eid, 1, 0, 0, room.tick + 1, "attack"))
        hits, seen = [], enemy.hit_seq
        for k, (at, to) in enumerate(path, 1):
            p.body.center_x, p.body.center_y = at
            enemy.body.center_x, enemy.body.center_y = to
            room.step()
            if enemy.hit_seq > seen:
                assert enemy.hit_seq == seen + 1, "one hit a tick at most from one hitbox"
                hits.append(k)
            seen = enemy.hit_seq
        assert p.attack_seq == 1 and not p.hitboxes, "one attack, its hitbox expired"
        return hits
    finally:
        room.leave(eid)
        enemy.state, enemy.body.center_x, enemy.body.center_y, enemy.hit_seq = saved


def scenarios(room: SceneRoom) -> dict[str, tuple[list[tuple[tuple[float, float], tuple[float, float]]], list[int]]]:
    """name: (path over 6 updates, the updates single-player's hitbox hits on). The attacker starts at A, facing
    right; its hitbox is at A + (range, 0)."""
    a = (400.0, 256.0)
    box = (a[0] + room.reach, a[1])
    later = (a[0] + 60.0, a[1])  # where the attacker walks to: its own hitbox would now be at later + (range, 0)
    found: dict[str, tuple[list[tuple[tuple[float, float], tuple[float, float]]], list[int]]] = {}
    for k in range(1, 7):  # the target steps into the hitbox on update k: hit while the hitbox lives
        found[f"enters on update {k}"] = ([(a, FAR if i < k else box) for i in range(1, 7)], [k] if k < 4 else [])
    found["stays inside"] = ([(a, box)] * 6, [1])
    found["leaves and comes back"] = ([(a, box), (a, FAR), (a, box), (a, box), (a, FAR), (a, box)], [1])
    walk = [(a[0] - 20.0 * i, a[1]) for i in range(6)]  # the attacker walks away; the target arrives later
    found["attacker walks away, target arrives"] = ([(walk[i], FAR if i < 2 else box) for i in range(6)], [3])
    found["attacker walks on, target at its new reach"] = (
        [(a, FAR)] + [(later, (later[0] + room.reach, later[1]))] * 5, [])
    return found


def test_the_hitbox_lifetime_is_single_players_at_the_authoritys_step() -> None:
    """ceil(0.2 s * HZ) = 4 updates: the 4th removes it, so the first 3 check (engine.behaviours.hitbox.Hitbox)."""
    assert hitbox_ticks() == math.ceil(0.2 * wire.HZ) == 4
    assert [hitbox_ticks(hz) for hz in (10, 30, 60)] == [2, 7, 13]  # (the Hitbox's own float sums: 6.000..01 at 30)


@pytest.mark.parametrize("case", ["enters on update 1", "enters on update 2", "enters on update 3",
                                  "enters on update 4", "enters on update 5", "enters on update 6", "stays inside",
                                  "leaves and comes back", "attacker walks away, target arrives",
                                  "attacker walks on, target at its new reach"])
def test_the_servers_hitbox_hits_as_single_players(case: str, coop: SceneRoom, monkeypatch: pytest.MonkeyPatch) -> None:
    """OD10, at equal deltas: the same updates hit in both runtimes, the hitbox stays where it was made (the attacker
    walking off doesn't take it along), it lives as long, and it hits each target once however long it overlaps."""
    path, expected = scenarios(coop)[case]
    assert single_player_hits(coop, path, monkeypatch) == expected, "single-player (the reference)"
    assert server_hits(coop, path) == expected, "the authority"


def test_rapid_attacks_never_duplicate_an_attack_or_a_hit(coop: SceneRoom) -> None:
    """An attack input every tick (and several a tick): the server starts an attack once per cooldown, and each
    attack's hitbox hits the bandit once."""
    room = coop
    eid = room.join()
    enemy = room.enemies[BANDIT]
    saved = (enemy.state, enemy.hit_seq)
    enemy.state = TargetState(hp=1000.0, max_hp=1000.0)
    place(room, eid, 568.0, 256.0, 0)
    try:
        seq, start, started = 0, enemy.hit_seq, []
        p = room.players[eid]
        for i in range(3 * room.cooldown + 1 + 10):  # (a flood, then quiet ticks while what waits drains)
            for _ in range(3 if i <= 3 * room.cooldown else 0):
                seq += 1
                room.input(eid, wire.input_frame(eid, seq, 0, 0, room.tick + 1, "attack"))
            before = p.attack_seq
            room.step()
            if p.attack_seq > before:
                started.append(room.tick)
        assert p.attack_seq == len(started) == 4 and len(p.attacks) == 0, "one attack a cooldown"
        assert all(b - a >= room.cooldown for a, b in zip(started, started[1:])), "never closer than the cooldown"
        assert enemy.hit_seq - start == p.attack_seq, "each attack's hitbox hits once"
        assert enemy.state.hp == 1000.0 - p.attack_seq
    finally:
        room.leave(eid)
        enemy.state, enemy.hit_seq = saved


# --- the window's presentation on the virtual clock -------------------------------------------------------------


class View:
    """SceneView's presentation calls, recorded (time ms, ...)."""

    def __init__(self, clock: list[float]) -> None:
        self.clock, self.swings, self.flashes = clock, [], []

    def swing(self, eid: int, own: bool) -> None:
        self.swings.append((self.clock[0], eid, own))

    def flash(self, enemy: str) -> None:
        self.flashes.append((self.clock[0], enemy))

    def near_drop(self, *_args: Any) -> bool:
        return False


def window(**attrs: Any) -> Any:
    """A window as the arenas' handlers read it: their action queue (Arena.act) and the attributes given."""
    arena: Any = SimpleNamespace(**{"action_keys": set(), "actions": [], "directions": {}, "keys": [], **attrs})
    arena.act = lambda action, tick=None: Arena.act(arena, action, tick)
    return arena


def scene_arena(entity: int, state: wire.Message, now: list[float]) -> Any:
    """What SceneArena.press, Arena.release and SceneArena.on_state read of a window."""
    arena = window(client=SimpleNamespace(entity=entity, state=state), arcade=SimpleNamespace(key=KEYS),
                   feedback=Feedback(), view=View(now), clock=lambda: now[0] / 1000)
    arena.view.room = SimpleNamespace(cooldown=0)  # (set by the caller)
    return arena


def presses(rng: random.Random, start: float, until: float) -> list[float]:
    """Bursts of rapid presses (every 50 ms for 400 ms), a burst every 1.6-1.7 s: every burst's first press swings,
    the rest fall in the co-op room's 0.5 s cooldown."""
    found, t = [], start
    while t < until:
        found.extend(t + 50.0 * i + rng.uniform(0, 10) for i in range(8))
        t += 1600.0 + rng.uniform(0, 100)
    return found


def mashing(rng: random.Random, start: float, until: float) -> list[float]:
    """Space mashed about every 70 ms (50-90 ms), as a player holds the attack rhythm against the cooldown: a swing on
    the first press each cooldown allows, so attacks reach the server as close together as the cooldown permits."""
    found, t = [], start
    while t < until:
        found.append(t)
        t += 70.0 + rng.uniform(-20, 20)
    return found


def play(profile: tuple[float, float, float], seed: int, when: list[float],
         stall: tuple[float, float] | None = None) -> dict[str, Any]:
    """The window (SceneArena's press and on_state; the send loop takes Arena.next_action, as Arena.session does) next
    to the bandit, over the probe's link, pressing Space at ``when`` (ms): what it showed and sent, and what the
    server did with each swing's attack (``outcomes``: its meant tick -> "run", "stale" or "refused"). ``stall``: (start,
    end) ms in which the server runs no tick (its event loop blocked), and skips the ticks it missed, as
    mesh_net.server.Server._run_clock does."""
    rtt, jitter, loss = profile
    now = [0.0]
    sent: list[float] = []
    claims: list[tuple[float, int]] = []  # (press ms, meant tick) of each swing shown
    outcomes: dict[int, str] = {}
    arena: Any = None
    last: list[Any] = [None]

    def intent(t: float, shown: list[Any]) -> tuple[Any, ...]:
        action, tick = Arena.next_action(arena)  # (Arena.session's send loop)
        if action == "attack":
            sent.append(t)
        return 0, 0, action, tick

    def frame(t: float, s: Session) -> None:
        nonlocal arena
        now[0] = t
        if arena is None:
            arena = scene_arena(s.eid, s.latest, now)
            arena.view.room.cooldown = s.room.cooldown
            SceneArena.on_state(arena, s.latest, s.eid, True)
        elif s.latest is not last[0]:
            SceneArena.on_state(arena, s.latest, s.eid, False)
        last[0] = s.latest
        arena.client.state = s.latest
        for p in [p for p in when if t - FRAME_MS < p <= t]:  # (the frame's dispatch_events reads the press)
            before = len(arena.view.swings)
            SceneArena.press(arena, SPACE, 0)
            Arena.release(arena, SPACE, 0)
            if len(arena.view.swings) > before:
                claims.append((p, arena.actions[-1][1]))

    with coop_room() as room:
        room.enemies[BANDIT].state = TargetState(hp=100_000.0, max_hp=100_000.0)
        judge, step = room._may_attack, room.step

        def may_attack(p: Any, meant: int) -> bool:
            stale = room.stale_attacks
            started = judge(p, meant)
            outcomes[meant] = "run" if started else "stale" if room.stale_attacks > stale else "refused"
            return started

        def stalled_step() -> None:
            if stall is None or not stall[0] <= s.now < stall[1]:
                step()

        room._may_attack, room.step = may_attack, stalled_step  # type: ignore[method-assign]
        s = Session(room, rtt, jitter, loss, seed, intent=intent, frame=frame,
                    setup=lambda room, eid: place(room, eid, 568.0, 256.0, 0))
        s.run(when[-1] + 3000.0)
        hits = room.enemies[BANDIT].hit_seq
        # hit count n -> virtual ms of the server tick that made it (each hit takes 1 HP; tick k runs at k / HZ s)
        hit_at = {n: min(t for t, pose in s.poses.items() if pose["hp"][BANDIT] <= 100_000.0 - n) * 1000 / wire.HZ
                  for n in range(1, hits + 1)}
        return {"swings": [t for t, eid, own in arena.view.swings if own and eid == s.eid], "sent": sent,
                "attacks": room.players[s.eid].attack_seq, "hits": hits, "hit_at": hit_at,
                "flashes": [t for t, _enemy in arena.view.flashes], "stale": room.stale_attacks,
                "refused": room.refused_attacks, "cooldown": room.cooldown, "claims": claims, "outcomes": outcomes}


@pytest.mark.parametrize("seed", [7, 8, 9])
@pytest.mark.parametrize("profile", PROFILES, ids=lambda p: f"rtt{p[0]}-jitter{p[1]}-loss{p[2]}")
def test_the_swing_shows_within_a_frame_and_a_hit_only_once_confirmed(seed: int, profile: tuple[float, float, float],
                                                                      ) -> None:
    """Bursts of presses: each press outside the cooldown swings on the frame that reads it (within one frame of the
    press) and is sent; a press in the cooldown shows nothing and sends nothing; a flash only on a frame after a
    snapshot whose hit count rose, never before the server's hit reached the window; one server attack per swing and
    one hit per attack."""
    rtt, jitter, _loss = profile
    for session in range(2):
        when = presses(random.Random(seed * 1000 + session), 1000.0, 9000.0)
        got = play(profile, seed * 100 + session, when)
        swings, hits = got["swings"], got["hits"]
        bursts = [p for i, p in enumerate(when) if i % 8 == 0]
        assert len(swings) == len(bursts), "each burst's first press swings, and only it"
        for p, t in zip(bursts, swings):
            assert 0.0 <= t - p <= FRAME_MS + 1e-9, f"swing {t - p:.1f} ms after its press"
        assert len(got["sent"]) == len(swings), "every swing's attack is sent, and no press in the cooldown"
        assert got["attacks"] == len(swings), "the server starts each attack shown, once"
        assert hits == got["attacks"], "each attack hits the bandit once"
        assert len(got["flashes"]) == hits, "every confirmed hit flashes, once"
        for n, t in enumerate(got["flashes"], 1):  # (n: the hit count that flash confirms)
            assert t >= got["hit_at"][n] + max(0.0, rtt / 2 - jitter), "a flash only after the hit reached the window"
        assert all(t > swing for t, swing in zip(got["flashes"], swings)), "the swing first, then (later) its hit"


MASHING_PROFILES = (*PROFILES[:4], (100, 10, 0.0), PROFILES[4])  # (+ jitter alone at 100 ms: the review's case)


@pytest.mark.parametrize("seed", [7, 8, 9])
@pytest.mark.parametrize("profile", MASHING_PROFILES, ids=lambda p: f"rtt{p[0]}-jitter{p[1]}-loss{p[2]}")
def test_mashing_never_shows_a_swing_the_server_does_not_run(seed: int, profile: tuple[float, float, float]) -> None:
    """Space mashed for 19 s against the cooldown, the attack rhythm as tight as it allows: jitter and TCP's bunching
    bring attack inputs to the server closer together than the cooldown. Judged on the ticks the window meant them for
    (SceneRoom._may_attack), every swing shown is an attack the server starts within owner decision OD1's envelope (to
    100 ms RTT, +-10 ms, 1% loss): none refused in the cooldown, none stale. At 200 ms with 1% loss a claim can read
    older than ATTACK_CAP (two ticks beyond it, measured): such a swing is stale, dropped and counted, never run late,
    and never refused; every other swing runs. Each starts once and hits once, no faster than the cooldown allows."""
    for session in range(2):
        got = play(profile, seed * 100 + session, mashing(random.Random(seed * 1000 + session), 1000.0, 20000.0))
        swings = got["swings"]
        assert len(swings) >= 19 * 1000 / (got["cooldown"] * 1000 / wire.HZ) * 0.9, "the cooldown's rhythm, kept"
        # (a cooldown of the window's reckoned ticks: in its own time, less at most the tick a sooner snapshot moves
        # the reckoning on, and the frame that reads the press)
        tick_ms = 1000 / wire.HZ
        assert all(b - a >= got["cooldown"] * tick_ms - tick_ms - FRAME_MS for a, b in zip(swings, swings[1:]))
        assert got["refused"] == 0, "no swing shown is refused in the cooldown"
        if profile[0] <= 100:
            assert got["stale"] == 0, "none stale within OD1's envelope"
        assert len(swings) == len(got["sent"]) == got["attacks"] + got["stale"], "every other swing shown starts"
        assert all(got["outcomes"][claim] in ("run", "stale") for _, claim in got["claims"])
        assert got["hits"] == got["attacks"], "each hits once"


@pytest.mark.parametrize("stall_ms", [200, 450, 1000])
@pytest.mark.parametrize("seed", [7, 8, 9])
@pytest.mark.parametrize("profile", MASHING_PROFILES, ids=lambda p: f"rtt{p[0]}-jitter{p[1]}-loss{p[2]}")
def test_after_a_server_stall_every_swing_shown_runs_again(stall_ms: int, seed: int,
                                                           profile: tuple[float, float, float]) -> None:
    """Mashing through a server stall (its event loop blocked 200, 450 or 1000 ms at 5 s): the server skips the ticks
    it missed, so its tick falls behind the clock and the window's reckoning runs ahead; the reckoning comes back down
    once RECKONING snapshots in a row have come late (Feedback.update), never swinging early. A swing shown during the
    stall or just after it may be refused (counted: at most 3 here); every swing pressed from RECKONING snapshots (a
    second) plus a round trip after the stall runs (or, at 200 ms, is stale), as without a stall."""
    from mesh_net.scene_room import RECKONING

    stall = (5000.0, 5000.0 + stall_ms)
    got = play(profile, seed, mashing(random.Random(seed * 1000), 1000.0, 20000.0), stall)
    recovered = stall[1] + RECKONING * 1000 / wire.HZ + profile[0]
    after = [(t, claim) for t, claim in got["claims"] if t >= recovered]
    assert len(after) >= 20
    allowed = ("run", "stale") if profile[0] > 100 else ("run",)
    assert [(t, got["outcomes"].get(claim)) for t, claim in after if got["outcomes"].get(claim) not in allowed] == []
    assert got["refused"] <= 3, "refused only around the stall"
    tick_ms = 1000 / wire.HZ
    swings = got["swings"]
    assert all(b - a >= got["cooldown"] * tick_ms - tick_ms - FRAME_MS for a, b in zip(swings, swings[1:])), \
        "never a swing early: its cooldown runs from the last swing's tick as sent"


def test_a_press_in_the_cooldown_never_swings_and_the_world_window_waits_for_its_room() -> None:
    """Feedback mirrors the room's cooldown on the room's tick, as the window reckons it from snapshots. WorldArena
    swings (and sends) only in the room on screen: a press while a room loads does nothing."""
    feedback = Feedback()
    feedback.baseline({"tick": 100, "players": [], "enemies": []}, 20, 10.0)  # 1 s at 20 Hz; tick 100 seen at 10 s
    assert feedback.press(10.0) == 100
    assert feedback.press(10.5) is None and feedback.press(10.99) is None
    assert feedback.press(11.0) == 120, "the meant tick: the one seen, advanced by the time since"
    feedback.update({"tick": 140, "players": [], "enemies": []}, 1, 11.9)  # (a snapshot that came sooner)
    assert feedback.tick(11.9) == 140 and feedback.press(11.9) == 140
    view = View([0.0])
    keys = SimpleNamespace(SPACE=SPACE, E=E, P=1, I=2, Y=3, N=4, L=5, ESCAPE=6, F2=7, R=8)
    arena = window(arcade=SimpleNamespace(key=keys), phase="loading", request=None, view=view, shown="start:1",
                   room="start:2", entity=1, feedback=Feedback(), clock=lambda: 50.0, note=lambda _e: None,
                   connected=True)
    arena.feedback.baseline({"tick": 7, "players": [], "enemies": []}, 20, 50.0)
    WorldArena.press(arena, SPACE, 0)
    assert arena.actions == [] and not view.swings, "no swing while the next room loads"
    arena.action_keys.clear()
    arena.phase, arena.shown = "playing", "start:2"
    WorldArena.press(arena, SPACE, 0)
    assert arena.actions == [("attack", 7)] and view.swings == [(0.0, 1, True)]
    arena.actions, arena.action_keys = [], set()
    WorldArena.press(arena, SPACE, 0)  # (the same instant: in the cooldown)
    assert arena.actions == [] and len(view.swings) == 1


def test_e_right_after_space_never_replaces_the_attack() -> None:
    """Space then E before the next input goes out (in both arenas): the attack whose swing showed and the use are
    both sent, in order, one an input."""
    own = [1, 0.0, 0.0, 0, 0, None, 0, 0]
    state = {"tick": 30, "players": [own], "enemies": [], "drops": []}
    scene = scene_arena(1, state, [5000.0])
    scene.view.room.cooldown = 10
    SceneArena.on_state(scene, state, 1, True)
    SceneArena.press(scene, SPACE, 0)
    SceneArena.press(scene, E, 0)
    assert scene.actions == [("attack", 30), ("use", None)] and len(scene.view.swings) == 1
    view = View([0.0])
    world = window(arcade=SimpleNamespace(key=SimpleNamespace(SPACE=SPACE, E=E, P=1, I=2, Y=3, N=4, L=5, ESCAPE=6,
                                                                F2=7, R=8)),
                   phase="playing", request=None, view=view, shown="start:1", room="start:1", entity=1, state=state,
                   feedback=Feedback(), clock=lambda: 5.0, note=lambda _e: None, connected=True, _own=lambda: own)
    world.feedback.baseline(state, 10, 5.0)
    WorldArena.press(world, SPACE, 0)
    WorldArena.press(world, E, 0)
    assert world.actions == [("attack", 30), ("use", None)] and len(view.swings) == 1


def test_losing_focus_releases_keys_but_keeps_the_pressed_actions() -> None:
    """Arena.blur (the window loses focus): held keys are released (none sticks), but an attack whose swing showed is
    still sent; a session's end clears what it never sent."""
    arena = window(keys=[1, 2], actions=[("attack", 9)])
    arena.action_keys = {32}
    Arena.blur(arena)
    assert arena.keys == [] and arena.action_keys == set() and arena.actions == [("attack", 9)]


def test_the_server_never_drops_an_attack_for_a_use_in_the_same_tick(coop: SceneRoom) -> None:
    """An attack and a use (or take) in one tick, either first: both run, the attack that tick; actions queue, one of
    each kind a tick, so none replaces another."""
    room = coop
    eid = room.join()
    enemy = room.enemies[BANDIT]
    saved = (enemy.state, enemy.hit_seq)
    enemy.state = TargetState(hp=100.0, max_hp=100.0)
    place(room, eid, 568.0, 256.0, 0)
    dropped = room.dropped_actions
    try:
        for seq, action in ((1, "use"), (2, "attack"), (3, "take"), (4, "use")):
            room.input(eid, wire.input_frame(eid, seq, 0, 0, room.tick, action))
        p = room.players[eid]
        assert p.attacks == [room.tick] and p.actions == ["use", "take", "use"]
        room.step()
        assert p.attack_seq == 1 and enemy.hit_seq == 1 and p.actions == ["take", "use"], "the attack, and the use"
        room.step()
        room.step()
        assert p.actions == [] and room.dropped_actions == dropped
    finally:
        room.leave(eid)
        enemy.state, enemy.hit_seq = saved


def test_the_cooldown_is_judged_on_the_meant_tick_within_its_cap(coop: SceneRoom) -> None:
    """SceneRoom._may_attack: an attack meant for a tick a cooldown after the last starts whenever it arrives within
    ATTACK_CAP ticks; one meant earlier is refused (the cooldown); one older than ATTACK_CAP is stale (dropped,
    counted, never run); one meant for a tick not reached counts as now. (A liar's gain:
    test_a_lying_client_gains_one_caps_worth_at_most.)"""
    from mesh_net.scene_room import ATTACK_CAP

    room = coop
    eid = room.join()
    p = room.players[eid]
    counts = (room.stale_attacks, room.refused_attacks)
    seq = 0

    def attack(meant: int) -> bool:
        nonlocal seq
        seq += 1
        before = p.attack_seq
        room.input(eid, wire.input_frame(eid, seq, 0, 0, meant, "attack"))
        room.step()
        return p.attack_seq > before

    try:
        for _ in range(40):
            room.step()
        c, now = room.cooldown, room.tick
        assert c + 3 < ATTACK_CAP + 3 < 40
        first = now + 1 - ATTACK_CAP  # (read next tick, as old as the cap allows)
        assert attack(first), "meant ATTACK_CAP ticks before it is read: on time"
        assert not attack(first + c - 1), "within the cooldown of the meant tick: refused"
        assert attack(first + c), "a cooldown after it by meant ticks, though it runs 2 ticks after: starts"
        assert room.refused_attacks - counts[1] == 1
        for _ in range(3 * c):
            room.step()
        assert not attack(room.tick - ATTACK_CAP), "read more than the cap after its tick: stale"
        assert room.stale_attacks - counts[0] == 1
        for _ in range(3 * c):
            room.step()
        assert attack(room.tick), "meant for now"
        far = room.tick + 1000
        assert not attack(far), "a far-future claim counts as now: within the last one's cooldown"
        for _ in range(3 * c):
            room.step()
        assert attack(far), "a far-future claim counts as now: it starts once the cooldown has passed"
        assert not attack(room.tick + 5), "and its cooldown runs from the tick it counted as, not the claim"
    finally:
        room.leave(eid)


@pytest.mark.parametrize("cooldown", [2, 3, 5, 10])
def test_a_lying_client_gains_one_caps_worth_at_most(cooldown: int, coop: SceneRoom) -> None:
    """A greedy liar: after a pause, one attack input every tick claiming the oldest tick the server accepts
    (max(attack_after, now - ATTACK_CAP)). Its run of attacks on consecutive ticks is 1 + ATTACK_CAP // (cooldown - 1)
    (13 at a cooldown of 2, 7 at 3, 4 at 5, 2 at 10); over any W ticks it starts at most 1 + (W + ATTACK_CAP) //
    cooldown, against an honest client's 1 + W // cooldown; and in the long run it keeps the honest rate."""
    from mesh_net.scene_room import ATTACK_CAP

    room = coop
    saved = room.cooldown
    room.cooldown = cooldown

    def starts(claim: Any, ticks: int = 400) -> list[int]:
        eid = room.join()
        p = room.players[eid]
        try:
            for _ in range(100):  # (a pause)
                room.step()
            found = []
            for seq in range(1, ticks + 1):
                room.input(eid, wire.input_frame(eid, seq, 0, 0, max(0, claim(p, room.tick + 1)), "attack"))
                before = p.attack_seq
                room.step()
                if p.attack_seq > before:
                    found.append(room.tick)
            return found
        finally:
            room.leave(eid)

    try:
        liar = starts(lambda p, next_tick: max(p.attack_after, next_tick - ATTACK_CAP))
        honest = starts(lambda p, next_tick: next_tick)
        stale = room.stale_attacks
        backdated = starts(lambda p, next_tick: p.attack_after)  # (claims older than the cap: refused as stale)
        assert room.stale_attacks > stale and len(backdated) <= len(liar)
        for i, first in enumerate(backdated):
            assert sum(1 for t in backdated[i:] if t <= first + 40) <= 1 + (40 + ATTACK_CAP) // cooldown
        run = next(k for k in range(1, len(liar)) if liar[k] != liar[0] + k)
        assert run == 1 + ATTACK_CAP // (cooldown - 1), "its run on consecutive ticks"
        for i, first in enumerate(liar):
            for w in range(0, 120):
                assert sum(1 for t in liar[i:] if t <= first + w) <= 1 + (w + ATTACK_CAP) // cooldown
        assert len(liar) <= len(honest) + 1 + ATTACK_CAP // cooldown + 1, "one cap's worth over 400 ticks"
        late = [t for t in liar if t > liar[0] + 200]
        assert len(late) <= 1 + (late[-1] - late[0]) // cooldown, "after the burst, the honest rate"
        assert all(b > a for a, b in zip(liar, liar[1:])), "never two a tick"
    finally:
        room.cooldown = saved


def rows(state: wire.Message, hit_seq: int | None = None, attack_seq: dict[int, int] | None = None) -> wire.Message:
    """``state`` with every enemy's hit count, or some players' attack counts, set."""
    return {**state,
            "enemies": [[r[0], r[1], r[2] if hit_seq is None else hit_seq, *r[3:]] for r in state["enemies"]],
            "players": [[*r[:7], (attack_seq or {}).get(r[0], r[7])] for r in state["players"]]}


def test_a_resume_takes_a_new_baseline(coop: SceneRoom) -> None:
    """N6: a welcome (a resume's too) is a new baseline: hits and swings that happened while away never flash or
    swing on the first state after it; only what changes after it does."""
    room = coop
    a, b = room.join(), room.join()
    try:
        state = room.snapshot()
        arena = scene_arena(a, state, [0.0])
        arena.view.room.cooldown = room.cooldown
        SceneArena.on_state(arena, rows(state, 1, {b: 1}), a, True)
        SceneArena.on_state(arena, rows(state, 1, {b: 1}), a, False)
        assert not arena.view.flashes and not arena.view.swings
        SceneArena.on_state(arena, rows(state, 4, {b: 3}), a, True)  # resumed: three more hits while away
        SceneArena.on_state(arena, {**rows(state, 4, {b: 3}), "tick": state["tick"] + 1}, a, False)
        assert not arena.view.flashes and not arena.view.swings, "nothing from before the resume"
        SceneArena.on_state(arena, rows(state, 5, {b: 4}), a, False)
        assert [e for _, e in arena.view.flashes] == [BANDIT] and [(e, o) for _, e, o in arena.view.swings] == [(b, False)]
    finally:
        room.leave(a)
        room.leave(b)


def test_every_enter_takes_a_new_baseline() -> None:
    """N7: each enter is another room instance with its own counters, so the window takes them anew: a hit counted in
    the last room never hides (or invents) one in the next, even for the same enemy id."""
    with disposable_project(expedition_files(), scaffold=False) as root:
        world = World(root)
    key = next(k for k, d in world.defs.items() if d.proto.enemies)
    first, second = world._create(key, 1), world._create(key, 2)
    enemy = sorted(first.room.enemies)[0]
    first.room.enemies[enemy].hit_seq = 5
    ids = {k: d.proto.identity for k, d in world.defs.items()}
    view = View([0.0])
    arena: Any = SimpleNamespace(identities=ids, defs=world.defs, room=None, key=None, entity=None, state=None,
                                 playback=None, pending=None, phase="playing", feedback=Feedback(), seq=0,
                                 actions=[], view=view, shown=None)

    def enter(inst: Any) -> int:
        eid = inst.room.join()
        WorldArena.on_frame(arena, {"v": wire.VERSION, "type": "enter", "room": inst.id, "key": key, "entity": eid,
                                    "state": inst.room.snapshot()}, 0.0)
        arena.shown = inst.id
        return eid

    def tick(inst: Any) -> None:
        inst.room.step()
        WorldArena.on_frame(arena, {"v": wire.VERSION, "type": "room_state", "room": inst.id,
                                    "state": inst.room.snapshot()}, 0.1)

    enter(first)
    tick(first)
    assert not view.flashes, "the enemy's hits before the enter are the baseline"
    arena.actions = [("attack", 3), ("use", None)]  # (pressed in the first room, never sent)
    enter(second)
    assert arena.actions == [], "what was pressed in the last room is never sent into this one"
    tick(second)
    assert not view.flashes
    second.room.enemies[enemy].hit_seq = 1  # the first hit in this instance: below the last room's 5, yet a hit
    tick(second)
    assert [e for _, e in view.flashes] == [enemy]


def test_a_room_still_loading_shows_no_swing_or_hit_and_later_none_of_its_past() -> None:
    """WorldArena: while the view still shows the last room (the next one loading), a state's swings and hits are
    counted but never shown (they belong to a room not on screen); once the room shows, only what happens after."""
    with disposable_project(expedition_files(), scaffold=False) as root:
        world = World(root)
    key = next(k for k, d in world.defs.items() if d.proto.enemies)
    inst = world._create(key, 1)
    enemy = sorted(inst.room.enemies)[0]
    ids = {k: d.proto.identity for k, d in world.defs.items()}
    view = View([0.0])
    arena: Any = SimpleNamespace(identities=ids, defs=world.defs, room=None, key=None, entity=None, state=None,
                                 playback=None, pending=None, phase="loading", feedback=Feedback(), seq=0, actions=[],
                                 view=view, shown="start:1")
    eid, peer = inst.room.join(), inst.room.join()
    WorldArena.on_frame(arena, {"v": wire.VERSION, "type": "enter", "room": inst.id, "key": key, "entity": eid,
                                "state": inst.room.snapshot()}, 0.0)

    def tick(hits: int, swings: int) -> None:
        inst.room.enemies[enemy].hit_seq, inst.room.players[peer].attack_seq = hits, swings
        inst.room.step()
        WorldArena.on_frame(arena, {"v": wire.VERSION, "type": "room_state", "room": inst.id,
                                    "state": inst.room.snapshot()}, 0.1)

    tick(2, 1)
    assert view.flashes == [] and view.swings == [], "nothing shown while the room loads"
    arena.shown = inst.id  # (the room shows)
    tick(2, 1)
    assert view.flashes == [] and view.swings == [], "and none of it later"
    tick(3, 2)
    assert [e for _, e in view.flashes] == [enemy] and [(e, o) for _, e, o in view.swings] == [(peer, False)]


def test_the_views_swing_and_flash_present_as_combat_and_the_hitbox_do(coop: SceneRoom) -> None:
    """SceneView.swing: Combat's attack animation (its priority and time), its attack sound at the avatar, rumble
    only for the window's own player; flash: the enemy tinted, the Hitbox's hit sound, and the tint undone once the
    flash's time is over. (Sound calls are recorded, never played.)"""
    from mesh_net.scene_client import FLASH_S, FLASH_TINT, HIT_SOUND
    from tests.test_mesh_net_hd2d import headless_view

    view = headless_view(coop)
    audio, rumble = MagicMock(), MagicMock()
    view.window = SimpleNamespace(hd2d_renderer=None, on_draw=lambda: None, audio=audio,
                                  input_controller=SimpleNamespace(manager=SimpleNamespace(rumble=rumble)))
    enemy = SimpleNamespace(center_x=600.0, center_y=256.0, color=(255, 255, 255), visible=True)
    view.sprites, view.enemy_colors = {BANDIT: enemy}, {BANDIT: (255, 255, 255)}
    own = SimpleNamespace(center_x=10.0, center_y=20.0, mesh_animator=object(), mesh_entity_data={})
    peer = SimpleNamespace(center_x=30.0, center_y=40.0, mesh_animator=object(), mesh_entity_data={})
    view.avatars = {1: own, 2: peer}
    view.swing(1, own=True)
    assert own.mesh_entity_data["animation_state"] == coop.combat["attack_anim"] == "attack"
    assert own.mesh_entity_data["_animation_state_meta"] == {"priority": 10.0, "timer": 0.5}
    audio.play_world_sfx.assert_called_once_with(coop.combat["attack_sound"], world_pos=(10.0, 20.0),
                                                 window=view.window, base_volume=0.5, profile="attack")
    rumble.assert_called_once_with(0.2, 0.03, 0)
    view.swing(2, own=False)
    assert peer.mesh_entity_data["animation_state"] == "attack" and rumble.call_count == 1, "no rumble for a peer"
    view.swing(99, own=False)  # (no avatar yet: nothing)
    audio.reset_mock()
    view.flash(BANDIT)
    assert enemy.color == FLASH_TINT
    audio.play_world_sfx.assert_called_once_with(HIT_SOUND, world_pos=(600.0, 256.0), window=view.window,
                                                 base_volume=0.6, profile="melee")
    view.sync(None, {}, None, FLASH_S / 2)
    assert enemy.color == FLASH_TINT, "still flashing"
    view.sync(None, {}, None, FLASH_S / 2 + 0.01)
    assert enemy.color == (255, 255, 255) and view.flashes == {}, "the tint undone"


def test_a_transfer_from_a_long_running_room_lets_the_first_press_swing() -> None:
    """N7: from a room far into its ticks to a fresh one (its tick count starts again): the last swing's tick belongs
    to the old room's count, so the new room's first press swings at once, and the server runs it there."""
    with disposable_project(expedition_files(), scaffold=False) as root:
        world = World(root)
    for _ in range(2000):
        world.hub.room.step()
    pid, _token = world.connect(None)
    m = world.members[pid]
    old = world.instances[m.instance]
    ids = {k: d.proto.identity for k, d in world.defs.items()}
    view = View([0.0])
    clock = [100.0]
    keys = SimpleNamespace(SPACE=SPACE, E=E, P=1, I=2, Y=3, N=4, L=5, ESCAPE=6, F2=7, R=8)
    arena = window(identities=ids, defs=world.defs, room=None, key=None, entity=None, state=None, playback=None,
                   pending=None, phase="playing", feedback=Feedback(), seq=0, view=view, shown=None,
                   arcade=SimpleNamespace(key=keys), request=None, note=lambda _e: None, connected=True,
                   clock=lambda: clock[0])
    (enter,) = [f for f in world.take(pid) if f["type"] == "enter"]
    WorldArena.on_frame(arena, enter, clock[0])
    arena.shown, arena.phase = arena.room, "playing"  # (the window's next draw shows the room)
    WorldArena.press(arena, SPACE, 0)
    assert arena.actions and arena.actions[-1][1] >= 2000, "a swing in the old room, at its tick"
    arena.actions.clear()
    arena.action_keys.clear()
    key = next(k for k, d in world.defs.items() if d.proto.enemies and k != old.key)
    fresh = world._create(key, 1)
    assert world._move(m, old, fresh, fresh.room.spawn)
    clock[0] += 0.2
    (enter,) = [f for f in world.take(pid) if f["type"] == "enter"]
    WorldArena.on_frame(arena, enter, clock[0])
    arena.shown, arena.phase = arena.room, "playing"  # (the window's next draw shows the room)
    WorldArena.press(arena, SPACE, 0)
    assert len(view.swings) == 2, "the first press in the fresh room swings"
    (action, tick), = arena.actions
    world.input(pid, wire.input_frame(m.eid, 1, 0, 0, tick, action, room=fresh.id))
    world.step()
    assert fresh.room.players[m.eid].attack_seq == 1, "and the server runs it there"


def test_leaving_a_room_drops_what_was_waiting() -> None:
    """SceneRoom.leave: attacks, uses and takes still waiting are dropped with the session (never run on a resume)."""
    with disposable_project(coop_files(), scaffold=False) as root:
        room = SceneRoom(root / COOP_SCENE, root)
    eid = room.join()
    place(room, eid, 568.0, 256.0, 0)
    room.input(eid, wire.input_frame(eid, 1, 0, 0, room.tick, "attack"))
    room.input(eid, wire.input_frame(eid, 2, 0, 0, room.tick, "use"))
    player = room.leave(eid)
    assert player.attacks == [] and player.actions == []
    back = room.join(player)
    room.step()
    assert room.players[back].attack_seq == 0 and room.enemies[BANDIT].hit_seq == 0, "nothing ran after the resume"


def test_a_sessions_end_drops_the_windows_unsent_actions() -> None:
    """Arena.session and WorldArena.session: when a session ends (here its connection fails), actions pressed in it and
    not yet sent are dropped, never sent in a resumed session or into another room."""
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]  # (nothing listens there once closed)
    keys = SimpleNamespace(**{n: i for i, n in enumerate("W UP S DOWN A LEFT D RIGHT SPACE E ESCAPE F2 R N".split())})
    scene = Arena(SimpleNamespace(push_handlers=lambda **_kw: None), SimpleNamespace(key=keys))
    scene.actions = [("attack", 7), ("use", None)]
    asyncio.run(scene.session(port))
    assert scene.actions == [] and "Disconnected" in scene.status
    world = window(port=None, token=None, character=None, note=lambda _e: None, status="", phase="playing",
                   room="start:1", pending=None, requests=[], actions=[("attack", 7), ("take", None)])
    world.blur = lambda: Arena.blur(world)
    asyncio.run(WorldArena.session(world, port))
    assert world.actions == [] and world.phase == "disconnected"


def test_a_flood_of_uses_stays_bounded_on_both_sides(coop: SceneRoom) -> None:
    """Uses at the input rate limit (mesh_net.server.InputBudget: 40 a second, two an input tick) against one read a
    tick: the server keeps at most PENDING waiting (the rest dropped, counted), and so does the window."""
    from mesh_net.scene_room import PENDING

    room = coop
    eid = room.join()
    dropped = room.dropped_actions
    try:
        seq = 0
        for _ in range(40):  # 2 s
            for _ in range(2):
                seq += 1
                room.input(eid, wire.input_frame(eid, seq, 0, 0, room.tick, "use"))
                assert len(room.players[eid].actions) <= PENDING
            room.step()
        assert room.dropped_actions - dropped >= 40 - PENDING
    finally:
        room.leave(eid)
    arena = window()
    for _ in range(40):
        Arena.act(arena, "use")
    assert len(arena.actions) == PENDING


def test_a_full_queue_never_drops_a_shown_swing() -> None:
    """Four uses waiting (the window's PENDING), then Space: the swing shows and its attack is queued all the same,
    and it rides the next input, ahead of the uses (its meant tick ages while it waits)."""
    from mesh_net.scene_room import PENDING

    own = [1, 0.0, 0.0, 0, 0, None, 0, 0]
    state = {"tick": 30, "players": [own], "enemies": [], "drops": []}
    arena = scene_arena(1, state, [5000.0])
    arena.view.room.cooldown = 10
    SceneArena.on_state(arena, state, 1, True)
    for _ in range(PENDING + 2):
        SceneArena.press(arena, E, 0)
        arena.action_keys.clear()
    assert arena.actions == [("use", None)] * PENDING
    SceneArena.press(arena, SPACE, 0)
    assert len(arena.view.swings) == 1 and ("attack", 30) in arena.actions
    assert Arena.next_action(arena) == ("attack", 30) and Arena.next_action(arena) == ("use", None)


def test_attacks_bunched_by_tcp_run_in_the_order_sent(coop: SceneRoom) -> None:
    """Two attack inputs a cooldown apart (by meant ticks) reach the server in one tick (a retransmission bunched
    them): the server reads the oldest first, so both run, one a tick; read newest first, the older would be refused."""
    from mesh_net.scene_room import ATTACK_CAP

    room = coop
    eid = room.join()
    p = room.players[eid]
    try:
        for _ in range(40):
            room.step()
        first = room.tick + 1 - ATTACK_CAP
        for seq, meant in ((1, first), (2, first + room.cooldown)):
            room.input(eid, wire.input_frame(eid, seq, 0, 0, meant, "attack"))
        refused = room.refused_attacks
        room.step()
        room.step()
        assert p.attack_seq == 2 and room.refused_attacks == refused and p.attacks == []
    finally:
        room.leave(eid)
