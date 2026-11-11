"""How the real-window networking tests walk an avatar to a place: by the authoritative position, both ways.

A window's held key reaches the server late: the test's command, the window's next frame and its next input frame
all come first. On a slow hosted runner that is a few ticks (7.5 px each), so "hold until past y, then release"
lands well past y. Two Windows failures did exactly that: a DOWN aimed just above the bottom of a gate's gap stopped
at y 242.5 (Extended 43008772085) and 241 (43016671504), the feet then caught the wall beside the gap (they pass only
for y 248-300), and the next RIGHT stopped at x 406.5, never reaching the door or the bandit.

``walk`` decides only once the avatar has stopped (the same position across two server ticks), so a late release
is seen before the next decision. Each leg lets go early by how far the previous leg went on after its release
(none for the first) and walks back after an overshoot; it gives up after ``ATTEMPTS`` legs. A player that can't
move or can't get there (blocked, input lost) still fails the test. It converges while a leg's carry stays under the band's width (``2 * within``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

AXES = {"RIGHT": (0, 1), "LEFT": (0, -1), "UP": (1, 1), "DOWN": (1, -1)}
BACK = {"RIGHT": "LEFT", "LEFT": "RIGHT", "UP": "DOWN", "DOWN": "UP"}
ATTEMPTS = 12
POLL = 0.005

# Where the window tests walk to, as (target, within), from the rooms' collision (tests/test_mesh_net_walk.py walks
# each one in both rooms, at several delays). The avatar's feet are its collider: 19 x 12 px, 18 px below its centre.
GAP = (274.0, 24.0)  # both gates' gaps (walls at y 224 and 288) pass centres y 248-300: 2 px to spare each side
ABOVE = (300.0, 24.0)  # a row clear above an enemy's feet (y 232-244): from y 268 up nothing of it blocks
ON_ENEMY = (268.0, 6.0)  # walking DOWN onto an enemy within 16 px of its x stops at y 268, facing it: a strike lands


async def walk(send: Callable[[str], Awaitable[Any]], key: str, target: float, within: float,
               where: Callable[[], Awaitable[tuple[int, float, float]]], timeout: float = 15,
               record: list[Any] | None = None) -> float:
    """Walk until the avatar has stopped within ``within`` px of ``target`` on ``key``'s axis.

    ``send(command)`` sends ``press KEY`` / ``release KEY`` to the avatar's window (it has the key down or up when
    the reply comes back); ``where()`` returns ``(tick, x, y)``: a server tick and the avatar's authoritative
    position at it, from the server itself or from a window's copy of its snapshot (later, never different).
    Stopped means the same position across two ticks. Returns the final coordinate. ``record`` (when given) gets
    each settled walk's legs ``(key, from, carry)``: the carries are how far releases landed late, in px (7.5 a tick).
    """
    axis = AXES[key][0]
    log: list[tuple[str, float, float]] = []

    async def sample() -> tuple[int, float]:
        tick, x, y = await where()
        return tick, float(y if axis else x)

    async def until(predicate: Callable[[float], bool], what: str) -> float:
        try:
            async with asyncio.timeout(timeout):
                while not predicate(here := (await sample())[1]):
                    await asyncio.sleep(POLL)
                return here
        except TimeoutError as exc:
            raise AssertionError(f"{key} to {target}: {what} not reached in {timeout} s (legs {log})") from exc

    async def stopped() -> float:
        try:
            async with asyncio.timeout(timeout):
                since, still = await sample()
                while True:
                    await asyncio.sleep(POLL)
                    tick, here = await sample()
                    if here != still:
                        since, still = tick, here
                    elif tick - since >= 2:
                        return here
        except TimeoutError as exc:
            raise AssertionError(f"{key} to {target}: the avatar stopping not reached in {timeout} s (legs {log})") from exc

    carry = 0.0  # how far the last leg went on after its release was sent: the next one lets go that much early
    released = None
    for _ in range(ATTEMPTS):
        here = await stopped()
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
            await until(lambda pos, start=here: pos != start, f"{step} from {here} moving")
            released = await until(lambda pos: (target - pos) * sign <= carry, f"{step} from {here} arriving")
        finally:
            await send(f"release {step}")
    raise AssertionError(f"{key} to {target} within {within}: not settled after {ATTEMPTS} legs {log}")
