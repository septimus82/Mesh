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

    def _between(self, now: float) -> tuple[wire.Message, wire.Message, wire.Message, float]:
        """The latest state, the two states either side of the cursor (two ticks behind; never going back) and how far
        it is between them."""
        latest = self.states[-1]
        self.cursor = min(latest["tick"], max(self.cursor, self.states[0]["tick"],
                          latest["tick"] - 2 + (now - self.arrival) * wire.HZ))
        left = next(s for s in reversed(self.states) if s["tick"] <= self.cursor)
        right = next(s for s in self.states if s["tick"] >= self.cursor)
        return latest, left, right, (self.cursor - left["tick"]) / max(1, right["tick"] - left["tick"])

    def positions(self, now: float) -> dict[int, tuple[Any, ...]]:
        """Each player's (x, y) two ticks behind; for a scene room's rows (mesh_net.protocol v2 and on) (x, y,
        elevation, floor): the elevation interpolated with x and y, the floor the nearer state's."""
        if not self.states:
            return {}
        latest, left, right, alpha = self._between(now)
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

    def enemies(self, now: float) -> dict[str, tuple[float, float, float, Any]]:
        """A scene room's enemies (wire v3 rows ``[id, hp, hit_seq, x, y, elevation, floor]``) as players are shown:
        (x, y, elevation) two ticks behind, interpolated, the floor the nearer state's (M4-4: they walk on the server;
        never predicted)."""
        if not self.states or "enemies" not in self.states[-1]:
            return {}
        latest, left, right, alpha = self._between(now)
        before = {r[0]: r for r in left["enemies"]}
        after = {r[0]: r for r in right["enemies"]}
        result: dict[str, tuple[float, float, float, Any]] = {}
        for row in latest["enemies"]:
            a, b = before.get(row[0], row), after.get(row[0], row)
            result[row[0]] = (a[3] + alpha * (b[3] - a[3]), a[4] + alpha * (b[4] - a[4]), a[5] + alpha * (b[5] - a[5]),
                              (a if alpha < 0.5 else b)[6])
        return result
