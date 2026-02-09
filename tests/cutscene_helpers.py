"""Shared test helpers for CutsceneRunner tests.

Provides:
- MockFlags, MockEventBus — lightweight test doubles.
- make_script — builds a minimal valid cutscene script dict.
- advance_cutscene_time — performs the two-phase "priming + advance" tick
  sequence required by the deterministic CutsceneRunner wait design.

Import from here rather than re-declaring mocks per test module.
"""
from __future__ import annotations

from typing import Any

from engine.cutscene_runtime.runner import CutsceneRunner
from engine.cutscene_runtime.schema import CUTSCENE_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Mock doubles
# ---------------------------------------------------------------------------

class MockFlags:
    """Mock flag provider/setter for testing."""

    def __init__(self, initial: dict[str, bool] | None = None) -> None:
        self._flags = dict(initial or {})

    def get_flag(self, name: str, default: bool = False) -> bool:
        return self._flags.get(name, default)

    def set_flag(self, name: str, value: bool) -> None:
        self._flags[name] = value

    def get_all(self) -> dict[str, bool]:
        return dict(self._flags)


class MockEventBus:
    """Mock event bus for testing."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def emit(self, event_type: str, **payload: Any) -> dict[str, Any]:
        event = {"type": event_type, "payload": payload}
        self.events.append(event)
        return event

    def clear(self) -> None:
        self.events.clear()

    def filter(self, event_type: str) -> list[dict[str, Any]]:
        return [e for e in self.events if e["type"] == event_type]

    def count(self, event_type: str | None = None) -> int:
        if event_type is None:
            return len(self.events)
        return len(self.filter(event_type))


# ---------------------------------------------------------------------------
# Script builder
# ---------------------------------------------------------------------------

def make_script(
    commands: list[dict[str, Any]],
    script_id: str = "test_script",
) -> dict[str, Any]:
    """Create a minimal valid cutscene script dict."""
    return {
        "schema_version": CUTSCENE_SCHEMA_VERSION,
        "id": script_id,
        "commands": commands,
    }


# ---------------------------------------------------------------------------
# Wait-priming helper
# ---------------------------------------------------------------------------

def advance_cutscene_time(runner: CutsceneRunner, dt: float) -> list[dict[str, Any]]:
    """Advance a CutsceneRunner by *dt*, handling wait-priming automatically.

    The deterministic CutsceneRunner uses a two-phase wait design:

    1. **Priming tick** — The first ``tick()`` that encounters a ``wait``
       command stores ``wait_remaining`` but does **not** subtract ``dt``
       from it (the runner breaks out of the command loop immediately).
    2. **Subsequent ticks** — ``dt`` is subtracted from ``wait_remaining``
       until the wait completes.

    This helper detects when the runner has just entered a wait (i.e.
    ``wait_remaining`` was 0 before the tick but is now > 0) and
    automatically issues the priming tick with ``dt=0.0``, then applies the
    real ``dt`` so callers don't need ad-hoc two-step sequences.

    **This does not change runtime semantics** — it simply encapsulates the
    priming convention for test / headless-simulation clarity.

    Returns the **combined** list of events emitted across both ticks (if a
    priming tick was needed) or the single tick.
    """
    was_waiting = runner._state.wait_remaining > 0

    # If we are NOT already mid-wait, do a priming tick first so that if the
    # next command is a wait, it gets stored before we try to subtract dt.
    if not was_waiting and runner.is_running:
        priming_events = runner.tick(0.0)
        # If the priming tick completed the cutscene or we're not now waiting,
        # the real dt tick is still needed.
        if runner._state.wait_remaining > 0:
            real_events = runner.tick(dt)
            return priming_events + real_events
        # No wait was encountered — apply the real dt normally.
        if runner.is_running:
            real_events = runner.tick(dt)
            return priming_events + real_events
        return priming_events

    # Already mid-wait — just tick.
    return runner.tick(dt)
