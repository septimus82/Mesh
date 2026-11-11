"""How a real-window networking test drops a world window (F2) and resumes it (R), knowing it saw the resumed session.

A probe's ``press``/``release`` reply does not mean the window has handled the key: pyglet queues a key event
dispatched outside the window's own event dispatch, and the window's loop takes it on its next frame. During F2 that
loop is busy closing the old session (52 ms on a hosted runner), while the probe still answers with the old session:
phase "playing", the same room, the same one player, the old entity. N7 waited for "Layer 2 with one player" after R,
which that pre-drop reply already satisfied: it took entity 2, and the window then drew its resumed entity 3
(Extended 43049464084).

``drop_and_resume`` waits on each step: the window's own disconnect and the server's record of it, then the
server's record of the resume, then the window showing the server's new avatar for that player in that room.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

POLL = 0.025


async def drop_and_resume(command: Callable[[str], Awaitable[dict[str, Any]]], world: Any, pid: int, room: str,
                          away: Callable[[], Awaitable[Any]] | None = None, timeout: float = 15) -> dict[str, Any]:
    """Drop and resume player ``pid``'s window; return the window's first reply from the resumed session.

    ``command`` sends one probe command to the window (``state`` / ``press KEY`` / ``release KEY``) and returns its
    reply; ``world`` is the in-process server's mesh_net.world.World; ``room`` the instance the player must resume
    into; ``away`` (optional) runs while the player is disconnected (e.g. another window seeing them leave).
    """
    m = world.members[pid]
    since = time.monotonic()

    def events() -> list[tuple[str, str]]:
        return [(e[2], e[4]) for e in list(world.history) if e[3] == pid and e[1] >= since]

    async def until(what: str, ok: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
        reply: dict[str, Any] = {}
        try:
            async with asyncio.timeout(timeout):
                while not ok(reply := await command("state")):
                    await asyncio.sleep(POLL)
                return reply
        except TimeoutError as exc:
            seen = {k: reply.get(k) for k in ("phase", "player", "room", "key", "entity")}
            raise AssertionError(f"resume of P{pid}: {what} not reached in {timeout} s; window {seen}, server "
                                 f"{(m.online, m.eid, m.instance)}, events {events()}") from exc

    pre = await command("state")
    before = pre["entity"]
    assert pre["phase"] == "playing" and pre["player"] == pid and m.online, (pre["phase"], pre["player"], m.online)
    assert before == m.eid and pre["room"] == m.instance == room, (before, m.eid, pre["room"], m.instance, room)

    await command("press F2")
    await until("the disconnect", lambda r: r["phase"] == "disconnected" and not m.online
                and ("disconnect", room) in events())
    if away is not None:
        await away()
    await command("release F2")
    await command("press R")  # (handled while disconnected: only then does R resume)
    await command("release R")

    def resumed(r: dict[str, Any]) -> bool:
        if not m.online or not events() or events()[-1][0] != "resume":
            return False  # (a fresh join would be another player: "connect" with a new pid, this one still away)
        assert m.instance == room, f"P{pid} resumed into {m.instance}, not {room}"
        return (r["phase"] == "playing" and r["player"] == pid and r["entity"] == m.eid and r["room"] == m.instance
                and any(p[0] == m.eid for p in r["state"]["players"]))

    back = await until("the resumed session", resumed)
    assert back["entity"] != before, f"P{pid} still shows its pre-drop avatar {before}"
    return back
