"""The real-window networking tests' walking helper (tests/net_walk.py), against the rooms' real collision and a
window whose keys reach the server ``late`` ticks after the test's command (what a slow hosted runner does).

The first tests reproduce the two Windows failures from their own numbers: the old "hold until past y" driver,
with a release three ticks late, leaves the avatar below a gate's gap, and walking RIGHT then stops at x 406.5,
where both failed runs stopped. The rest require the new helper to get through the gap at every delay, to land
where the guardian's or bandit's strike connects, and to still fail when a player can't move.

Time here is simulated (tests/net_sim_time.py): the server's 20 ms ticks, the helper's 5 ms polls and its timeouts
all run on one simulated clock, so a test takes as long as its ticks take to compute. The last tests hold the
stand-in window and server to their own rules: a key takes effect exactly ``late`` ticks after its command, in the
order sent, and the server ticks once every 20 ms of simulated time."""

import asyncio
import copy

import pytest

from mesh_net.scene_room import COOP_SCENE, SceneRoom, coop_files, disposable_project
from mesh_net.world import World, expedition_files
from tests.net_sim_time import run as simulated
from tests.net_walk import ABOVE, GAP, ON_ENEMY, walk

pytestmark = pytest.mark.integration
DIRECTIONS = {"RIGHT": (1, 0), "LEFT": (-1, 0), "UP": (0, 1), "DOWN": (0, -1)}
PASSES = (248.0, 300.0)  # centre heights whose feet pass between the walls beside both gates (y 224 and 288)
TICK = 0.02
BLOCKED_X = 406.5  # where both failed runs' avatars stopped: feet against the wall below the gap


def ruins_1():
    with disposable_project(expedition_files(), scaffold=False) as root:
        world = World(root)
    return copy.deepcopy(world.defs["ancient_ruins_layer_1"].proto)


def ruins_2():
    with disposable_project(expedition_files(), scaffold=False) as root:
        world = World(root)
    return copy.deepcopy(world.defs["ancient_ruins_layer_2"].proto)


def coop():
    with disposable_project(coop_files(), scaffold=False) as root:
        return SceneRoom(root / COOP_SCENE, root)


class LateWindow:
    """One input frame a tick, as WorldArena and SceneArena send, with the held keys a ``press``/``release`` command
    changes taking effect ``late`` ticks after it. ``deaf``: no input frame ever arrives (a lost input path)."""

    def __init__(self, room, at, late, deaf=False, gate_open=True):
        self.room, self.late, self.deaf = room, late, deaf
        if gate_open:
            room.locked.clear()  # (the lever was pulled: both tests open the gate before going through it)
        self.eid = room.join()
        body = room.players[self.eid].body
        body.center_x, body.center_y = at
        self.pending, self.keys, self.seq = [], [], 0

    async def send(self, command):
        op, key = command.split()
        self.pending.append((self.room.tick + self.late, op, key))

    async def where(self):
        body = self.room.players[self.eid].body
        return self.room.tick, body.center_x, body.center_y

    def pos(self):
        body = self.room.players[self.eid].body
        return body.center_x, body.center_y

    def tick(self):
        for item in [p for p in self.pending if p[0] <= self.room.tick]:
            self.pending.remove(item)
            _, op, key = item
            if op == "press" and key not in self.keys:
                self.keys.append(key)
            elif op == "release" and key in self.keys:
                self.keys.remove(key)
        if not self.deaf:
            self.seq += 1
            dx, dy = DIRECTIONS[self.keys[-1]] if self.keys else (0, 0)
            self.room.input(self.eid, {"v": 1, "type": "input", "entity": self.eid, "seq": self.seq, "dx": dx, "dy": dy})
        self.room.step()


def play(window, driver, phase=0.0):
    """Run ``driver()`` while the server ticks every ``TICK`` s of simulated time (slower than the helper polls, as
    the real 20 Hz server is; ``late`` is counted in these ticks). ``phase``: how long after the driver starts the
    server's clock does, in seconds (where its ticks fall between the helper's polls)."""
    async def main():
        async def server():
            await asyncio.sleep(phase)
            while True:
                await asyncio.sleep(TICK)
                window.tick()

        task = asyncio.create_task(server())
        try:
            return await driver()
        finally:
            task.cancel()
    return simulated(main())


async def hold_until(window, key, predicate, limit=40):
    """The old driver: hold the key until the condition holds, then release. A wall stops it at ``limit`` ticks."""
    await window.send(f"press {key}")
    start = window.room.tick
    while not predicate(window.pos()) and window.room.tick - start < limit:
        await asyncio.sleep(0.001)
    await window.send(f"release {key}")
    stop = window.room.tick
    while window.room.tick - stop < window.late + 6:  # (the late release, then the movement lease)
        await asyncio.sleep(0.001)
    return window.pos()


@pytest.mark.parametrize(("room", "start", "threshold"), [(ruins_1, (352.0, 300.0), 258), (coop, (372.0, 320.0), 262)],
                         ids=["N7 Layer 1 (Extended 43008772085)", "N6 co-op scene (Extended 43016671504)"])
def test_the_old_driver_reproduces_both_failures(room, start, threshold):
    """DOWN to a one-sided threshold just above the gap's bottom, released three ticks late: the feet end below the
    gap, and RIGHT stops at the failed runs' x 406.5."""
    window = LateWindow(room(), start, late=3)

    async def driver():
        _, y = await hold_until(window, "DOWN", lambda p: p[1] <= threshold)
        x, _ = await hold_until(window, "RIGHT", lambda p: p[0] >= 470)
        return x, y

    x, y = play(window, driver)
    assert y < PASSES[0] and x == BLOCKED_X


@pytest.mark.parametrize("late", [0, 2, 4])
@pytest.mark.parametrize(("room", "start"), [(ruins_1, (352.0, 300.0)), (coop, (372.0, 327.5))], ids=["N7", "N6"])
def test_walk_lands_inside_the_gap_and_gets_through_at_every_delay(room, start, late):
    window = LateWindow(room(), start, late=late)

    async def driver():
        y = await walk(window.send, "DOWN", *GAP, window.where)
        x, _ = await hold_until(window, "RIGHT", lambda p: p[0] >= 470)
        return x, y

    x, y = play(window, driver)
    assert abs(y - GAP[0]) <= GAP[1] and PASSES[0] <= window.pos()[1] <= PASSES[1] and x >= 470


@pytest.mark.parametrize("late", [0, 2, 4])
@pytest.mark.parametrize(("room", "enemy", "route"), [
    (ruins_2, "ancient_ruins_layer_2_guardian_480_256_0_0", [((64.0, 160.0), "RIGHT", 430, 16), "UP", ("RIGHT", 480, 16)]),
    (coop, "start_bandit_608_256_0_0", [((392.0, 274.0), "RIGHT", 520, 24), "UP", ("RIGHT", 608, 16)]),
], ids=["N7 guardian", "N6 bandit"])
def test_walk_onto_the_enemy_from_above_lands_a_strike(room, enemy, route, late):
    """The window tests' route to each enemy, from where they start it (Layer 2's arrival; just past the co-op gate):
    up past its feet, over it, then down onto it. Its feet stop the avatar at y 268 facing it, and one attack takes a
    hit point. (Approached from the side, a strike lands only for y 216-260 and the enemy blocks only for 244-268:
    a late release left N8's avatar at y 265 beside the guardian, where its swing missed.)"""
    r = room()
    (start, key, target, within), _, (key2, target2, within2) = route
    window = LateWindow(r, start, late=late)

    async def driver():
        await walk(window.send, key, target, within, window.where)
        await walk(window.send, "UP", *ABOVE, window.where)
        await walk(window.send, key2, target2, within2, window.where)
        return await walk(window.send, "DOWN", *ON_ENEMY, window.where)

    assert play(window, driver) == 268.0
    player = r.players[window.eid]
    hp = r.enemies[enemy].state.hp
    r._attack(player)
    assert player.facing == 3 and r.enemies[enemy].state.hp == hp - r.damage


def test_walk_still_fails_when_input_never_arrives():
    window = LateWindow(coop(), (372.0, 327.5), late=0, deaf=True)
    with pytest.raises(AssertionError, match="moving"):
        play(window, lambda: walk(window.send, "DOWN", *GAP, window.where, timeout=1))


def test_walk_still_fails_when_a_wall_blocks_the_way():
    """Below the gap, RIGHT can't reach x 470: the avatar stops at the wall and the walk fails, never passes."""
    window = LateWindow(coop(), (372.0, 240.0), late=1)
    with pytest.raises(AssertionError, match="arriving"):
        play(window, lambda: walk(window.send, "RIGHT", 470, 12, window.where, timeout=1))
    assert window.pos()[0] == BLOCKED_X


def test_walk_gives_up_when_each_release_lands_later_than_the_last():
    """A window that gets one tick later with every release: allowing for the last leg's carry is never enough, the
    avatar swings wider each leg, and the walk stops at its limit of legs instead of going on."""
    window = LateWindow(coop(), (372.0, 300.0), late=0)

    async def send(command):
        await window.send(command)
        if command.startswith("release"):
            window.late += 1

    with pytest.raises(AssertionError, match="not settled after 12 legs") as failure:
        play(window, lambda: walk(send, "DOWN", 274.0, 3.0, window.where))
    assert "('UP', 232.5, 75.0)]" in str(failure.value)  # the twelfth leg, ten ticks of carry


# --- the stand-in window and server themselves -----------------------------------------------------------------------

STEP = 7.5  # px a tick
PHASES = (0.0, 0.0013, 0.0061, 0.0117, 0.0189)  # of the server's ticks against the helper's polls, in seconds


def sent(window, *commands):
    async def main():
        for command in commands:
            await window.send(command)
    simulated(main())


@pytest.mark.parametrize("late", [0, 2, 4])
def test_a_key_takes_effect_exactly_late_ticks_after_its_command(late):
    """Press, three ticks of movement, release: the avatar stays put for ``late`` ticks, then moves one step a tick
    until ``late`` ticks after the release, and not one tick more or less."""
    window = LateWindow(coop(), (372.0, 320.0), late=late)
    ys = []

    def ticks(n):
        for _ in range(n):
            window.tick()
            ys.append(window.pos()[1])

    sent(window, "press DOWN")
    ticks(late + 3)
    sent(window, "release DOWN")
    ticks(late + 4)
    assert ys == [320.0 - STEP * min(max(n + 1 - late, 0), late + 3) for n in range(2 * late + 7)]
    assert window.room.tick == 2 * late + 7 and not window.pending


def test_commands_sent_in_one_tick_take_effect_in_the_order_sent():
    window = LateWindow(coop(), (372.0, 320.0), late=1)
    sent(window, "press DOWN", "release DOWN")  # down, then up: never held
    for _ in range(4):
        window.tick()
    assert window.pos() == (372.0, 320.0) and window.keys == []
    sent(window, "press DOWN", "press LEFT", "release LEFT")  # the later key wins while held, then DOWN is left
    for _ in range(4):
        window.tick()
    assert window.pos() == (372.0, 320.0 - 3 * STEP) and window.keys == ["DOWN"]


def test_the_server_ticks_once_every_tick_of_simulated_time():
    window = LateWindow(coop(), (372.0, 320.0), late=0)
    step, at = window.tick, []

    def tick():
        at.append(asyncio.get_running_loop().time())
        step()
    window.tick = tick
    play(window, lambda: asyncio.sleep(1.01))
    assert window.room.tick == 50 and at == pytest.approx([TICK * n for n in range(1, 51)], abs=1e-9)


def test_walk_still_fails_when_the_server_never_ticks():
    window = LateWindow(coop(), (372.0, 327.5), late=0)
    window.tick = lambda: None
    with pytest.raises(AssertionError, match="the avatar stopping not reached in 1 s"):
        play(window, lambda: walk(window.send, "DOWN", *GAP, window.where, timeout=1))
    assert window.room.tick == 0 and window.pos() == (372.0, 327.5)


@pytest.mark.parametrize(("room", "start"), [(ruins_1, (352.0, 300.0)), (coop, (372.0, 327.5))], ids=["N7", "N6"])
def test_walk_gets_through_the_gap_wherever_the_ticks_fall_between_its_polls(room, start):
    """Real time put the server's ticks anywhere between the helper's polls; simulated time puts them where it is
    told to. Every delay at every phase: the walk lands inside the gap and RIGHT gets through."""
    fresh = room()
    for late in (0, 2, 4):
        for phase in PHASES:
            window = LateWindow(copy.deepcopy(fresh), start, late=late)

            async def driver(window=window):
                y = await walk(window.send, "DOWN", *GAP, window.where)
                x, _ = await hold_until(window, "RIGHT", lambda p: p[0] >= 470)
                return x, y

            x, y = play(window, driver, phase)
            assert abs(y - GAP[0]) <= GAP[1] and PASSES[0] <= window.pos()[1] <= PASSES[1] and x >= 470, (late, phase, x, y)
