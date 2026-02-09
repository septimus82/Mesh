"""Contract tests pinning CutsceneRunner two-phase wait semantics.

These tests document and enforce the invariant that:
1. The first tick encountering a wait stores the duration but does NOT
   subtract dt.
2. Subsequent ticks subtract dt until completion.
3. Behaviour is deterministic across repeated runs.
4. advance_cutscene_time correctly encapsulates the two-phase pattern.
"""
from __future__ import annotations

import pytest
from typing import Any

from engine.cutscene_runtime.runner import CutsceneRunner

from tests.cutscene_helpers import (
    MockFlags,
    MockEventBus,
    advance_cutscene_time,
    make_script,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_flags() -> MockFlags:
    return MockFlags()


@pytest.fixture
def mock_bus() -> MockEventBus:
    return MockEventBus()


@pytest.fixture
def runner(mock_bus: MockEventBus, mock_flags: MockFlags) -> CutsceneRunner:
    return CutsceneRunner(
        event_bus=mock_bus,
        flag_provider=mock_flags,
        flag_setter=mock_flags,
    )


# ---------------------------------------------------------------------------
# Raw two-phase contract (no helper)
# ---------------------------------------------------------------------------

class TestWaitTwoPhaseContract:
    """Pin the raw tick semantics so they can never silently change."""

    def test_first_tick_primes_wait_without_subtracting_dt(
        self, runner: CutsceneRunner
    ) -> None:
        """Tick that first encounters a wait stores duration, does NOT subtract dt."""
        script = make_script([
            {"type": "wait", "duration": 2.0},
            {"type": "stop"},
        ])
        runner.load_script(script)
        runner.start()

        # Before any tick, wait_remaining is 0.
        assert runner._state.wait_remaining == 0.0

        # Priming tick with dt=0 — sets wait_remaining to 2.0.
        runner.tick(0.0)
        assert runner._state.wait_remaining == 2.0
        assert runner._state.command_index == 0

    def test_subsequent_tick_subtracts_dt(self, runner: CutsceneRunner) -> None:
        """Second and later ticks subtract dt from wait_remaining."""
        script = make_script([
            {"type": "wait", "duration": 2.0},
            {"type": "stop"},
        ])
        runner.load_script(script)
        runner.start()

        runner.tick(0.0)  # prime
        assert runner._state.wait_remaining == 2.0

        runner.tick(0.5)
        assert runner._state.wait_remaining == pytest.approx(1.5)
        assert runner._state.command_index == 0

        runner.tick(1.5)
        assert runner._state.wait_remaining == 0.0
        assert runner._state.command_index == 1  # advanced past wait

    def test_determinism_across_repeated_runs(self, mock_bus: MockEventBus, mock_flags: MockFlags) -> None:
        """Same dt schedule always produces identical state."""
        script = make_script([
            {"type": "wait", "duration": 1.0},
            {"type": "emit_event", "event_type": "ping"},
            {"type": "wait", "duration": 0.5},
            {"type": "stop"},
        ])
        dt_schedule = [0.0, 0.3, 0.3, 0.4, 0.0, 0.5]

        results: list[list[float]] = []
        for _ in range(3):
            r = CutsceneRunner(
                event_bus=MockEventBus(),
                flag_provider=MockFlags(),
                flag_setter=MockFlags(),
            )
            r.load_script(script)
            r.start()
            trace: list[float] = []
            for dt in dt_schedule:
                r.tick(dt)
                trace.append(round(r._state.wait_remaining, 6))
            results.append(trace)

        # All three runs must produce the identical trace.
        assert results[0] == results[1] == results[2]


# ---------------------------------------------------------------------------
# advance_cutscene_time helper contract
# ---------------------------------------------------------------------------

class TestAdvanceCutsceneTimeHelper:
    """Ensure the helper correctly encapsulates the two-phase wait."""

    def test_helper_primes_and_advances_in_one_call(
        self, runner: CutsceneRunner
    ) -> None:
        """advance_cutscene_time(dt) primes wait then subtracts dt."""
        script = make_script([
            {"type": "wait", "duration": 2.0},
            {"type": "stop"},
        ])
        runner.load_script(script)
        runner.start()

        advance_cutscene_time(runner, 0.5)
        # wait_remaining should be 2.0 - 0.5 = 1.5
        assert runner._state.wait_remaining == pytest.approx(1.5)

    def test_helper_continues_mid_wait_without_extra_prime(
        self, runner: CutsceneRunner
    ) -> None:
        """If already mid-wait, helper does a single tick (no double prime)."""
        script = make_script([
            {"type": "wait", "duration": 2.0},
            {"type": "stop"},
        ])
        runner.load_script(script)
        runner.start()

        advance_cutscene_time(runner, 0.5)  # prime + 0.5 → remaining 1.5
        advance_cutscene_time(runner, 0.5)  # just tick → remaining 1.0
        assert runner._state.wait_remaining == pytest.approx(1.0)

    def test_helper_completes_wait_and_moves_on(
        self, runner: CutsceneRunner, mock_bus: MockEventBus
    ) -> None:
        """Helper lets the wait complete and the runner advance."""
        script = make_script([
            {"type": "wait", "duration": 0.5},
            {"type": "emit_event", "event_type": "done"},
            {"type": "stop"},
        ])
        runner.load_script(script)
        runner.start()

        events = advance_cutscene_time(runner, 0.6)
        assert runner.is_completed
        done_events = [e for e in mock_bus.events if e["type"] == "done"]
        assert len(done_events) == 1

    def test_helper_zero_duration_wait(self, runner: CutsceneRunner) -> None:
        """Zero-duration wait advances immediately through helper."""
        script = make_script([
            {"type": "wait", "duration": 0.0},
            {"type": "stop"},
        ])
        runner.load_script(script)
        runner.start()

        advance_cutscene_time(runner, 0.0)
        assert runner.is_completed

    def test_helper_returns_combined_events(
        self, runner: CutsceneRunner, mock_bus: MockEventBus
    ) -> None:
        """Events from both priming and real tick are returned."""
        script = make_script([
            {"type": "emit_event", "event_type": "before_wait"},
            {"type": "wait", "duration": 0.1},
            {"type": "stop"},
        ])
        runner.load_script(script)
        runner.start()

        # First call: priming tick runs emit_event + encounters wait,
        # then real tick starts subtracting.
        events = advance_cutscene_time(runner, 0.2)
        assert runner.is_completed
