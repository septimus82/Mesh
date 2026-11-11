"""The real-window tests' drop/resume synchronisation (tests/net_resume.py), against the real World and a window that
behaves as mesh_net.world_client driven by tooling/net_world_probe: a key command's reply comes before the window
handles the key (pyglet queues it for the window's next frame), and F2 holds that loop while the old session closes,
the probe still answering with the old session.

The first test reproduces Extended 43049464084 from its own numbers: N7's wait ("Layer 2, one player", after R)
takes the pre-drop reply, and the window then draws its resumed avatar instead. The rest require the new wait to
return the resumed session, and to fail when the resume, the identity, the room, the restored state or the window
process is wrong."""

import asyncio
import copy
import dataclasses

import pytest

from mesh_net.scene_room import disposable_project
from mesh_net.world import World, expedition_files
from tests.net_resume import POLL, drop_and_resume

pytestmark = pytest.mark.integration
LAYER_2, GUARDIAN = "ancient_ruins_layer_2", "ancient_ruins_layer_2_guardian_480_256_0_0"
FRAME = 0.005
CLOSE = 0.15  # the old session's close, while the window still shows it (52 ms in the failed run)


def staged():
    """A player in Layer 2 with its guardian dead, as N7's b is when it drops; returns (world, pid, token)."""
    with disposable_project(expedition_files(), scaffold=False) as root:
        world = World(root)
    pid, token = world.connect(None)
    m = world.members[pid]
    inst = world._create(LAYER_2, None)
    world._enter(m, inst, world.instances[m.instance].room.leave(m.eid))
    guardian = inst.room.enemies[GUARDIAN]
    guardian.state = dataclasses.replace(guardian.state, hp=0.0)
    world.take(pid)
    return world, pid, token


class QueuedWindow:
    """One world window: ``command`` answers at once (the probe), keys wait for the next frame of ``run`` (the
    window's loop). ``fault``: "no_resume" (R does nothing), "fresh" (R joins as a new player), "wrong_room" (the
    window shows another room than its enter named), "stale_state" (the window keeps its pre-drop state),
    "stale_avatar" (the scene keeps drawing the pre-drop avatar), "exit" (the window process dies at R)."""

    def __init__(self, world, pid, token, fault=None):
        m = world.members[pid]
        self.world, self.player, self.token, self.fault = world, pid, token, fault
        self.phase, self.room, self.entity = "playing", m.instance, m.eid
        self.key, self.state = world.instances[m.instance].key, world.instances[m.instance].room.snapshot()
        self.drawn, self.queue, self.pending = m.eid, [], None

    async def command(self, cmd):
        op, *key = cmd.split()
        if self.fault == "exit" and cmd == "press R":
            raise RuntimeError("window process exited with 1: []")
        if op in ("press", "release"):
            self.queue.append((op, key[0]))
        return {"phase": self.phase, "player": self.player, "room": self.room, "key": self.key,
                "entity": self.entity, "state": copy.deepcopy(self.state)}

    def capture(self):
        return {"drawn": {str(self.drawn): 1}}

    async def run(self):
        while True:
            await asyncio.sleep(FRAME)
            while self.queue:
                op, key = self.queue.pop(0)
                if (op, key, self.phase) == ("press", "F2", "playing"):
                    self.world.disconnect(self.player)  # the connection closes at once ...
                    await asyncio.sleep(CLOSE)  # ... and the loop waits for the close, the old session still shown
                    self.phase, self.room, self.pending = "disconnected", None, None
                elif (op, key, self.phase) == ("press", "R", "disconnected") and self.fault != "no_resume":
                    self.player, self.token = self.world.connect(None if self.fault == "fresh" else self.token)
                    self.phase = "loading"  # welcome
                    m = self.world.members[self.player]
                    self.pending = (m.instance, m.eid, self.world.take(self.player)[0])
            if self.pending is not None and self.room is None:  # the enter frame
                room, eid, enter = self.pending
                assert enter["type"] == "enter" and enter["entity"] == eid
                self.room = "elsewhere:9" if self.fault == "wrong_room" else room
                self.entity, self.key = eid, self.world.instances[room].key
                if self.fault != "stale_state":
                    self.state = enter["state"]
            elif self.pending is not None:  # the next frame loads and shows it
                self.phase, self.pending = "playing", None
                if self.fault != "stale_avatar":
                    self.drawn = self.entity


def play(window, driver):
    async def main():
        task = asyncio.create_task(window.run())
        try:
            return await driver()
        finally:
            task.cancel()
    return asyncio.run(main())


def test_the_old_wait_takes_the_pre_drop_reply():
    """N7's sequence: F2; the other window sees b away (the server's record); release F2; tap R; wait for Layer 2 with
    one player. The pre-drop session satisfies it, so it returns the old entity, and the scene then shows another."""
    world, pid, token = staged()
    window = QueuedWindow(world, pid, token)
    before = window.entity

    async def driver():
        await window.command("press F2")
        while world.members[pid].online:
            await asyncio.sleep(POLL)
        await window.command("release F2")
        await window.command("press R")
        await window.command("release R")
        while not ((r := await window.command("state"))["phase"] == "playing" and r["state"]
                   and r["key"] == LAYER_2 and len(r["state"]["players"]) == 1):
            await asyncio.sleep(POLL)
        while window.phase != "playing" or window.entity == before:  # (then the resume lands)
            await asyncio.sleep(POLL)
        return r

    back = play(window, driver)
    assert back["entity"] == before and back["room"] is not None  # the old session: room and avatar before the drop
    assert sorted(int(e) for e in window.capture()["drawn"]) != [back["entity"]]  # N7's shot() then failed


def test_the_new_wait_returns_the_resumed_session():
    world, pid, token = staged()
    window = QueuedWindow(world, pid, token)
    before, room = window.entity, window.room
    seen = []

    async def away():
        seen.append(world.members[pid].online)

    back = play(window, lambda: drop_and_resume(window.command, world, pid, room, away=away))
    m = world.members[pid]
    assert seen == [False] and m.online and back["player"] == pid
    assert back["entity"] == m.eid != before and back["room"] == room and back["key"] == LAYER_2
    assert back["state"]["enemies"] == [[GUARDIAN, 0.0]] and [p[0] for p in back["state"]["players"]] == [m.eid]
    assert sorted(int(e) for e in window.capture()["drawn"]) == [back["entity"]]
    assert [e[2] for e in world.history if e[3] == pid][-2:] == ["disconnect", "resume"]


@pytest.mark.parametrize(("fault", "match"), [
    ("no_resume", "the resumed session not reached"),
    ("fresh", "the resumed session not reached"),  # another player id: this one never comes back
    ("wrong_room", "the resumed session not reached"),
    ("stale_state", "the resumed session not reached"),
])
def test_the_new_wait_fails_when_the_resume_is_wrong(fault, match):
    world, pid, token = staged()
    window = QueuedWindow(world, pid, token, fault=fault)
    with pytest.raises(AssertionError, match=match):
        play(window, lambda: drop_and_resume(window.command, world, pid, window.room, timeout=1))


def test_the_new_wait_fails_when_the_server_resumes_elsewhere():
    """The party's room is gone by the time the player resumes: the server puts them in the hub, not Layer 2."""
    world, pid, token = staged()
    window = QueuedWindow(world, pid, token)
    room = window.room

    async def away():
        world._destroy(world.instances[room])

    with pytest.raises(AssertionError, match=f"resumed into start:1, not {room}"):
        play(window, lambda: drop_and_resume(window.command, world, pid, room, away=away, timeout=1))


def test_the_scene_check_still_fails_on_the_wrong_avatar():
    world, pid, token = staged()
    window = QueuedWindow(world, pid, token, fault="stale_avatar")
    back = play(window, lambda: drop_and_resume(window.command, world, pid, window.room))
    assert sorted(int(e) for e in window.capture()["drawn"]) != [back["entity"]]


def test_a_window_process_dying_is_not_swallowed():
    world, pid, token = staged()
    window = QueuedWindow(world, pid, token, fault="exit")
    with pytest.raises(RuntimeError, match="exited"):
        play(window, lambda: drop_and_resume(window.command, world, pid, window.room, timeout=1))
