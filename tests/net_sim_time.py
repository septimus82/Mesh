"""Simulated time for the networking tests whose server and window are both stand-ins (tests/test_mesh_net_walk.py and
the world half of tests/test_mesh_net_resume.py): no socket, no process, nothing that takes real time to answer.

Those tests waited on the wall clock for a simulated server to tick: 35 s for 0.2 s of simulation. ``run`` runs a
coroutine on an event loop of its own whose clock is simulated. Whenever every task is waiting on a timer, the clock
moves straight to the next timer instead of the process sleeping until it; ``asyncio.sleep``, ``asyncio.timeout`` and
``loop.time()`` on that loop all read the one simulated clock, so timers fire in the order they would in real time
(equal times: one fixed order, the same every run) and code under test runs unchanged. Nothing is patched: the loop exists for
one ``run`` call, and every other loop in the process keeps real time.

Not for anything with a real peer (a socket, a subprocess, a thread): its answer takes real time the simulated clock
would run past. Those tests keep ``asyncio.run``.

Guards: a wait nothing can end (no timer, nothing ready) fails at once, and a run that outlasts ``real_limit`` seconds
of real time (a loop that never waits) or ``simulated_limit`` seconds of simulated time (a poll with no timeout of its
own) fails with ``SimulationStuck``. The real limit is read from ``time.perf_counter()``, never the simulated clock
(and not ``time.monotonic()``, which Python 3.11 reads in 15.6 ms steps on Windows).
"""

from __future__ import annotations

import asyncio
import selectors
import time
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")
GRACE = 5.0  # real seconds a stuck run's tasks get to end once it has been failed


class SimulationStuck(AssertionError):
    """The simulated run can't finish: nothing left to wait for, or one of its limits passed."""


class _Clock(selectors.DefaultSelector):
    """The loop's selector, holding its clock: asked to wait ``timeout`` seconds for I/O, it adds them to the
    simulated time and only looks (the loop's own wake-up pipe is all it ever holds)."""

    def __init__(self, real_limit: float, simulated_limit: float) -> None:
        super().__init__()
        self.now = 0.0
        self.real_deadline = time.perf_counter() + real_limit
        self.real_limit, self.simulated_limit = real_limit, simulated_limit

    def select(self, timeout: float | None = None) -> list[tuple[selectors.SelectorKey, int]]:
        ready = super().select(0)
        if time.perf_counter() > self.real_deadline:
            self.real_deadline = time.perf_counter() + GRACE  # (so the run's tasks can be cancelled and the loop closed)
            raise SimulationStuck(f"still running after {self.real_limit} s of real time, at {self.now:.3f} s simulated")
        if ready:
            return ready
        if timeout is None:
            raise SimulationStuck(f"nothing can continue at {self.now:.3f} s simulated: every task waits, and not on a timer")
        self.now += max(0.0, timeout)
        if self.now > self.simulated_limit:
            self.simulated_limit = self.now + GRACE
            raise SimulationStuck(f"still running after {self.now:.0f} s of simulated time")
        return ready


class _Loop(asyncio.SelectorEventLoop):
    def __init__(self, real_limit: float, simulated_limit: float) -> None:
        self.clock = _Clock(real_limit, simulated_limit)
        super().__init__(self.clock)
        # A timer is due once the clock is within this of it. The real clock's value is the platform's (15.6 ms on
        # Windows, 1 ns on Linux), which would wake a 5 ms sleep early on one and not the other
        # (tests/test_mesh_net_sim_time.py holds this to the exact times on both).
        self._clock_resolution = 1e-9

    def time(self) -> float:
        return self.clock.now


def run(main: Coroutine[Any, Any, T], *, real_limit: float = 30.0, simulated_limit: float = 600.0) -> T:
    """``asyncio.run(main)`` on simulated time (as above). Returns its result; leaves no loop or task behind."""
    with asyncio.Runner(loop_factory=lambda: _Loop(real_limit, simulated_limit)) as runner:
        return runner.run(main)
