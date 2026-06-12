from __future__ import annotations

from engine.log_utils import (
    get_log_once_count,
    get_logger,
    log_once,
    reset_log_once_state,
)

_LOG = get_logger("engine.log_once")


def log_once_with_counter(key: str, msg: str) -> None:
    """
    Log a message only once per key, while counting all occurrences.
    """
    log_once(str(key), str(msg), logger=_LOG)


def get_log_count(key: str) -> int:
    """Return the total number of times a log key has been triggered."""
    return get_log_once_count(str(key))


def reset_log_counters() -> None:
    """Reset all log counters and seen keys (useful for tests)."""
    reset_log_once_state()

