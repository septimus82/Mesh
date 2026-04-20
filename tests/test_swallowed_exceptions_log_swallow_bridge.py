"""Regression tests for the _log_swallow -> record_swallowed bridge.

Task 5b Shape A: calls into the central _log_swallow made inside an
except block should automatically populate the record_swallowed
telemetry counter, even when the log-once gate suppresses the debug
log output.
"""
from __future__ import annotations

import pytest

from engine import swallowed_exceptions
from engine.swallowed_exceptions import _log_swallow

pytestmark = [pytest.mark.fast]


def test_log_swallow_records_exception_in_except_block():
    swallowed_exceptions.reset()
    try:
        raise ValueError("boom")
    except ValueError:
        _log_swallow("BRIDGE-001", "context", once=True)

    counts = swallowed_exceptions.read_counts()
    assert counts.get("BRIDGE-001") == 1


def test_log_swallow_outside_except_does_not_record():
    swallowed_exceptions.reset()
    _log_swallow("BRIDGE-002", "context-no-exc", once=True)

    counts = swallowed_exceptions.read_counts()
    assert "BRIDGE-002" not in counts


def test_log_swallow_records_even_when_once_gate_suppresses_log():
    swallowed_exceptions.reset()
    for _ in range(3):
        try:
            raise RuntimeError("repeating")
        except RuntimeError:
            _log_swallow("BRIDGE-003", "repeat", once=True)

    counts = swallowed_exceptions.read_counts()
    # All three calls record telemetry despite the once-gate suppressing
    # the debug log output for calls 2 and 3.
    assert counts.get("BRIDGE-003") == 3


def test_log_swallow_once_gate_still_dedupes_debug_log(monkeypatch):
    swallowed_exceptions.reset()
    debug_calls: list[tuple] = []

    def spy_debug(*args, **kwargs):
        debug_calls.append(args)

    monkeypatch.setattr(swallowed_exceptions._LOGGER, "debug", spy_debug)

    for _ in range(3):
        try:
            raise RuntimeError("repeating-log")
        except RuntimeError:
            _log_swallow("BRIDGE-004", "repeat-log", once=True)

    bridge_debug_calls = [c for c in debug_calls if "BRIDGE-004" in c]
    # Once-gate still fires: exactly one debug log for three calls.
    assert len(bridge_debug_calls) == 1


def test_log_swallow_once_false_logs_every_call(monkeypatch):
    swallowed_exceptions.reset()
    debug_calls: list[tuple] = []

    def spy_debug(*args, **kwargs):
        debug_calls.append(args)

    monkeypatch.setattr(swallowed_exceptions._LOGGER, "debug", spy_debug)

    for _ in range(3):
        try:
            raise RuntimeError("no-once")
        except RuntimeError:
            _log_swallow("BRIDGE-005", "no-once", once=False)

    bridge_debug_calls = [c for c in debug_calls if "BRIDGE-005" in c]
    assert len(bridge_debug_calls) == 3