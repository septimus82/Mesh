"""Display positions two simulation ticks behind the latest received state."""

from __future__ import annotations

from collections import deque

from . import protocol as wire


class Playback:
    def __init__(self) -> None:
        self.states: deque[wire.Message] = deque(maxlen=8)
        self.arrival = 0.0
        self.cursor = 0.0

    def push(self, state: wire.Message, now: float) -> bool:
        wire.snapshot(state)
        if self.states and state["tick"] <= self.states[-1]["tick"]:
            return False
        self.states.append(state)
        self.arrival = now
        return True

    def positions(self, now: float) -> dict[int, tuple[float, float]]:
        if not self.states:
            return {}
        latest = self.states[-1]
        self.cursor = min(latest["tick"], max(self.cursor, self.states[0]["tick"],
                          latest["tick"] - 2 + (now - self.arrival) * wire.HZ))
        left = next(s for s in reversed(self.states) if s["tick"] <= self.cursor)
        right = next(s for s in self.states if s["tick"] >= self.cursor)
        alpha = (self.cursor - left["tick"]) / max(1, right["tick"] - left["tick"])
        before = {p[0]: p[1:3] for p in left["players"]}
        after = {p[0]: p[1:3] for p in right["players"]}
        result = {}
        for eid, x, y in latest["players"]:
            ax, ay = before.get(eid, (x, y))
            bx, by = after.get(eid, (x, y))
            result[eid] = (ax + alpha * (bx - ax), ay + alpha * (by - ay))
        return result
