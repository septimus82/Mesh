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
        seq, start = 0, enemy.hit_seq
        ticks = 3 * room.cooldown + 1
        for _ in range(ticks):
            for _ in range(3):
                seq += 1
                room.input(eid, wire.input_frame(eid, seq, 0, 0, room.tick + 1, "attack"))
            room.step()
        attacks = math.ceil(ticks / room.cooldown)
        assert room.players[eid].attack_seq == attacks
        assert enemy.hit_seq - start == attacks
        assert enemy.state.hp == 1000.0 - attacks
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


def scene_arena(entity: int, state: wire.Message, now: list[float]) -> Any:
    """What SceneArena.press, Arena.release and SceneArena.on_state read of a window."""
    arena: Any = SimpleNamespace(client=SimpleNamespace(entity=entity, state=state), arcade=SimpleNamespace(key=KEYS),
                                 action_keys=set(), action=None, feedback=Feedback(), view=View(now),
                                 clock=lambda: now[0] / 1000, directions={}, keys=[])
    arena.view.room = SimpleNamespace(cooldown=0)  # (set by the caller)
    return arena


def presses(rng: random.Random, start: float, until: float) -> list[float]:
    """Bursts of rapid presses (every 50 ms for 400 ms), a burst every 1.6-1.7 s: every burst's first press swings,
    the rest fall in the co-op room's 0.5 s cooldown. (1.6 s exceeds the cooldown by more than a retransmission can
    bunch two attack inputs at 200 ms RTT (+400 ms), so the server starts every attack the window showed.)"""
    found, t = [], start
    while t < until:
        found.extend(t + 50.0 * i + rng.uniform(0, 10) for i in range(8))
        t += 1600.0 + rng.uniform(0, 100)
    return found


@pytest.mark.parametrize("seed", [7, 8, 9])
@pytest.mark.parametrize("profile", PROFILES, ids=lambda p: f"rtt{p[0]}-jitter{p[1]}-loss{p[2]}")
def test_the_swing_shows_within_a_frame_and_a_hit_only_once_confirmed(seed: int, profile: tuple[float, float, float],
                                                                      ) -> None:
    """The window (SceneArena's press and on_state; the send loop takes its latched action, as Arena.session does) next
    to the bandit, over the probe's link: each press outside the cooldown swings on the frame that reads it (within
    one frame of the press) and is sent; a press in the cooldown shows nothing and sends nothing; a flash only on a
    frame after a snapshot whose hit count rose, never before the server's hit; one server attack per swing and one
    hit per attack."""
    rtt, jitter, loss = profile
    now = [0.0]
    sent: list[float] = []
    for session in range(2):
        rng = random.Random(seed * 1000 + session)
        when = presses(rng, 1000.0, 9000.0)
        arena: Any = None
        last: list[Any] = [None]

        def intent(t: float, shown: list[Any]) -> tuple[int, int, str | None]:
            action, arena.action = arena.action, None  # (Arena.session's send loop)
            if action == "attack":
                sent.append(t)
            return 0, 0, action

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
                SceneArena.press(arena, SPACE, 0)
                Arena.release(arena, SPACE, 0)

        with coop_room() as room:
            room.enemies[BANDIT].state = TargetState(hp=1000.0, max_hp=1000.0)
            s = Session(room, rtt, jitter, loss, seed * 100 + session, intent=intent, frame=frame,
                        setup=lambda room, eid: place(room, eid, 568.0, 256.0, 0))
            sent.clear()
            s.run(when[-1] + 3000.0)
            server = room.players[s.eid]
            hits = room.enemies[BANDIT].hit_seq
        # hit count n -> virtual ms of the server tick that made it (each hit takes 1 HP; tick k runs at k / HZ s)
        hit_at = {n: min(t for t, pose in s.poses.items() if pose["hp"][BANDIT] <= 1000.0 - n) * 1000 / wire.HZ
                  for n in range(1, hits + 1)}
        swings = [t for t, eid, own in arena.view.swings if own and eid == s.eid]
        bursts = [p for i, p in enumerate(when) if i % 8 == 0]
        assert len(swings) == len(bursts), "each burst's first press swings, and only it"
        for p, t in zip(bursts, swings):
            assert 0.0 <= t - p <= FRAME_MS + 1e-9, f"swing {t - p:.1f} ms after its press"
        assert len(sent) == len(swings), "every swing's attack is sent, and no press in the cooldown"
        assert server.attack_seq == len(swings), "the server starts each attack shown, once"
        assert hits == server.attack_seq, "each attack hits the bandit once"
        flashes = [t for t, enemy in arena.view.flashes]
        assert len(flashes) == hits, "every confirmed hit flashes, once"
        for n, t in enumerate(flashes, 1):  # (n: the hit count that flash confirms)
            assert t >= hit_at[n] + max(0.0, rtt / 2 - jitter), "a flash only after the server's hit reached the window"
        assert all(t > swing for t, swing in zip(flashes, swings)), "the swing first, then (later) its hit"


def test_a_press_in_the_cooldown_never_swings_and_the_world_window_waits_for_its_room() -> None:
    """Feedback mirrors the room's cooldown on the window's clock. WorldArena swings (and sends) only in the room on
    screen: a press while a room loads does nothing."""
    feedback = Feedback()
    feedback.baseline({"players": [], "enemies": []}, 20)  # 1 s at 20 Hz
    assert feedback.press(10.0)
    assert not feedback.press(10.5) and not feedback.press(10.999)
    assert feedback.press(11.0)
    view = View([0.0])
    arena: Any = SimpleNamespace(arcade=SimpleNamespace(key=SimpleNamespace(SPACE=SPACE, E=E, P=1, I=2, Y=3, N=4,
                                                                            L=5, ESCAPE=6, F2=7, R=8)),
                                 directions={}, phase="loading", action_keys=set(), action=None, request=None,
                                 view=view, shown="start:1", room="start:2", entity=1, feedback=Feedback(),
                                 clock=lambda: 50.0, note=lambda _e: None, connected=True)
    arena.feedback.baseline({"players": [], "enemies": []}, 20)
    WorldArena.press(arena, SPACE, 0)
    assert arena.action is None and not view.swings, "no swing while the next room loads"
    arena.action_keys.clear()
    arena.phase, arena.shown = "playing", "start:2"
    WorldArena.press(arena, SPACE, 0)
    assert arena.action == "attack" and view.swings == [(0.0, 1, True)]
    arena.action, arena.action_keys = None, set()
    WorldArena.press(arena, SPACE, 0)  # (the same instant: in the cooldown)
    assert arena.action is None and len(view.swings) == 1


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
                                 playback=None, pending=None, phase="playing", feedback=Feedback(), seq=0, action=None,
                                 view=view, shown=None)

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
    arena.action = "attack"  # (pressed in the first room, never sent)
    enter(second)
    assert arena.action is None, "an attack pressed in the last room is never sent into this one"
    tick(second)
    assert not view.flashes
    second.room.enemies[enemy].hit_seq = 1  # the first hit in this instance: below the last room's 5, yet a hit
    tick(second)
    assert [e for _, e in view.flashes] == [enemy]
