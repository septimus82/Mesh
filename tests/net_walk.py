"""How the real-window networking tests walk an avatar to a place: by the server's own position, both ways.

A window's held key reaches the server late: the test's command, the window's next frame and its next input frame
all come first. On a slow hosted runner that is a few ticks (7.5 px each), so "hold until past y, then release"
lands well past y. Two Windows failures did exactly that: a DOWN aimed just above the bottom of a gate's gap stopped
at y 242.5 (Extended 43008772085) and 241 (43016671504), the feet then caught the wall beside the gap (they pass only
for y 248-300), and the next RIGHT stopped at x 406.5, never reaching the door or the bandit.

``walk`` decides on the authoritative position once the player has stopped, never on a window's (later) copy of
it. Each leg lets go early by how far the previous leg went on after its release (none for the first), walks back
after an overshoot, and it gives up after ``ATTEMPTS`` legs: a player that can't move or can't get there (blocked,
input lost) still fails the test. It converges while a leg's carry stays under the band's width (``2 * within``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

AXES = {"RIGHT": (0, 1), "LEFT": (0, -1), "UP": (1, 1), "DOWN": (1, -1)}
BACK = {"RIGHT": "LEFT", "LEFT": "RIGHT", "UP": "DOWN", "DOWN": "UP"}
ATTEMPTS = 12
LEASE = 5  # SceneRoom.step: a player keeps moving for wire.HZ // 4 ticks after its last moving input

# Where the window tests walk to, as (target, within), from the rooms' collision (tests/test_mesh_net_walk.py walks
# each one in both rooms, at several delays). The avatar's feet are its collider: 19 x 12 px, 18 px below its centre.
GAP = (274.0, 24.0)  # both gates' gaps (walls at y 224 and 288) pass centres y 248-300: 2 px to spare each side
ABOVE = (300.0, 24.0)  # a row clear above an enemy's feet (y 232-244): from y 268 up nothing of it blocks
ON_ENEMY = (268.0, 6.0)  # walking DOWN onto an enemy within 16 px of its x stops at y 268, facing it: a strike lands


async def until(predicate: Callable[[], Any], what: str, timeout: float = 15) -> Any:
    """Poll in-process (server) state until ``predicate()`` is truthy; AssertionError naming ``what`` otherwise."""
    try:
        async with asyncio.timeout(timeout):
            while not (got := predicate()):
                await asyncio.sleep(0.005)
            return got
    except TimeoutError as exc:
        raise AssertionError(f"{what}: not reached in {timeout} s") from exc


async def walk(send: Callable[[str], Awaitable[Any]], key: str, target: float, within: float,
               avatar: Callable[[], tuple[Any, Any]], timeout: float = 15, record: list[Any] | None = None) -> float:
    """Walk until the server has the avatar stopped within ``within`` px of ``target`` on ``key``'s axis.

    ``send(command)`` sends ``press KEY`` / ``release KEY`` to the avatar's window; ``avatar()`` returns
    ``(room, player)`` as the server has them now (``room.tick``; ``player.body``, ``dx``, ``dy``, ``last_input``).
    Returns the final authoritative coordinate. ``record`` (when given) gets each settled walk's legs
    ``(key, from, carry)``: the carries are how late the window's releases landed, in px (7.5 a tick)."""
    axis = AXES[key][0]

    def pos() -> float:
        body = avatar()[1].body
        return float(body.center_y if axis else body.center_x)

    def stopped() -> bool:
        room, player = avatar()
        return not (player.dx or player.dy) or room.tick - player.last_input > LEASE

    log: list[tuple[str, float, float]] = []
    carry = 0.0  # how far the last leg went on after its release was sent: the next one lets go that much early
    released = None
    for _ in range(ATTEMPTS):
        await until(stopped, f"{key} to {target}: the avatar stopping (legs {log})", timeout)
        here = pos()
        if released is not None:
            carry = abs(here - released)
        if abs(target - here) <= within:
            if record is not None:
                record.append({"to": [key, target, within], "at": here, "carry": carry, "legs": log})
            return here
        step = key if (target - here) * AXES[key][1] > 0 else BACK[key]
        sign = AXES[step][1]
        log.append((step, here, carry))
        await send(f"press {step}")
        try:
            await until(lambda start=here: pos() != start,
                        f"{key} to {target}: {step} from {here} moving (legs {log})", timeout)
            await until(lambda: (target - pos()) * sign <= carry,
                        f"{key} to {target}: {step} from {here} arriving (legs {log})", timeout)
        finally:
            released = pos()
            await send(f"release {step}")
    raise AssertionError(f"{key} to {target} within {within}: not settled after {ATTEMPTS} legs {log}, at {pos()}")
