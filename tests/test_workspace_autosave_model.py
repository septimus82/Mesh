"""Contract tests for workspace autosave model."""

from __future__ import annotations

from engine.editor.workspace_autosave_model import (
    AutosaveState,
    mark_flushed,
    schedule_change,
    should_flush,
)


def test_schedule_marks_pending() -> None:
    state = AutosaveState()
    next_state = schedule_change(state, 100)
    assert next_state.pending is True
    assert next_state.last_change_ns == 100
    assert next_state.last_save_ns == 0


def test_should_flush_respects_delay() -> None:
    state = AutosaveState(pending=True, last_change_ns=100, last_save_ns=0)
    assert should_flush(state, 150, 60) is False
    assert should_flush(state, 160, 60) is True


def test_mark_flushed_clears_pending() -> None:
    state = AutosaveState(pending=True, last_change_ns=100, last_save_ns=0)
    flushed = mark_flushed(state, 250)
    assert flushed.pending is False
    assert flushed.last_change_ns == 100
    assert flushed.last_save_ns == 250


def test_flush_once_per_burst() -> None:
    state = AutosaveState()
    state = schedule_change(state, 100)
    assert should_flush(state, 150, 60) is False
    assert should_flush(state, 160, 60) is True
    state = mark_flushed(state, 160)
    assert should_flush(state, 220, 60) is False

    state = schedule_change(state, 300)
    state = schedule_change(state, 330)
    assert should_flush(state, 380, 60) is False
    assert should_flush(state, 391, 60) is True
