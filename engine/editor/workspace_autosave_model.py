"""Pure helpers for debounced workspace autosave."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AutosaveState:
    pending: bool = False
    last_change_ns: int = 0
    last_save_ns: int = 0


def schedule_change(state: AutosaveState, now_ns: int) -> AutosaveState:
    """Record a workspace change that should trigger autosave after a delay."""
    now = _coerce_ns(now_ns)
    return AutosaveState(pending=True, last_change_ns=now, last_save_ns=state.last_save_ns)


def should_flush(state: AutosaveState, now_ns: int, delay_ns: int) -> bool:
    """Return True when the pending change should be flushed to disk."""
    if not state.pending:
        return False
    now = _coerce_ns(now_ns)
    delay = max(0, int(delay_ns))
    return (now - state.last_change_ns) >= delay


def mark_flushed(state: AutosaveState, now_ns: int) -> AutosaveState:
    """Mark the autosave as flushed."""
    now = _coerce_ns(now_ns)
    return AutosaveState(pending=False, last_change_ns=state.last_change_ns, last_save_ns=now)


def _coerce_ns(value: int) -> int:
    try:
        return int(value)
    except Exception:
        return 0
