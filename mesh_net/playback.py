"""Display positions two simulation ticks behind the latest received state."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Any

from . import protocol as wire


class Playback:
    def __init__(self, check: Callable[[wire.Message], None] = wire.snapshot) -> None:
        self.check = check
        self.states: deque[wire.Message] = deque(maxlen=8)
        self.arrival = 0.0
        self.cursor = 0.0

    def push(self, state: wire.Message, now: float) -> bool:
        self.check(state)
        if self.states and state["tick"] <= self.states[-1]["tick"]:
            return False
        self.states.append(state)
        self.arrival = now
        return True

    def positions(self, now: float) -> dict[int, tuple[Any, ...]]:
        """Each player's (x, y) two ticks behind; for a scene room's rows (mesh_net.protocol v2 and on) (x, y,
        elevation, floor): the elevation interpolated with x and y, the floor the nearer state's."""
        if not self.states:
            return {}
        latest = self.states[-1]
        self.cursor = min(latest["tick"], max(self.cursor, self.states[0]["tick"],
                          latest["tick"] - 2 + (now - self.arrival) * wire.HZ))
        left = next(s for s in reversed(self.states) if s["tick"] <= self.cursor)
        right = next(s for s in self.states if s["tick"] >= self.cursor)
        alpha = (self.cursor - left["tick"]) / max(1, right["tick"] - left["tick"])
        before = {p[0]: p for p in left["players"]}
        after = {p[0]: p for p in right["players"]}
        result: dict[int, tuple[Any, ...]] = {}
        for row in latest["players"]:
            a, b = before.get(row[0], row), after.get(row[0], row)
            at: tuple[Any, ...] = (a[1] + alpha * (b[1] - a[1]), a[2] + alpha * (b[2] - a[2]))
            if len(row) > 3:  # (a scene room's row)
                at += (a[4] + alpha * (b[4] - a[4]), (a if alpha < 0.5 else b)[5])
            result[row[0]] = at
        return result
