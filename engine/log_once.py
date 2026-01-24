from __future__ import annotations

from typing import Dict, Set

from engine.logging_tools import get_logger

_LOG_COUNTERS: Dict[str, int] = {}
_LOG_ONCE_SEEN: Set[str] = set()
_LOG = get_logger("engine.log_once")


def log_once_with_counter(key: str, msg: str) -> None:
    """
    Log a message only once per key, but track total occurrences.

    First occurrence logs the message.
    Subsequent occurrences only increment the internal counter.
    """
    count = _LOG_COUNTERS.get(key, 0) + 1
    _LOG_COUNTERS[key] = count

    if key not in _LOG_ONCE_SEEN:
        _LOG.info("%s", msg)
        _LOG_ONCE_SEEN.add(key)


def get_log_count(key: str) -> int:
    """Return the total number of times a log key has been triggered."""
    return _LOG_COUNTERS.get(key, 0)


def reset_log_counters() -> None:
    """Reset all log counters and seen keys (useful for tests)."""
    _LOG_COUNTERS.clear()
    _LOG_ONCE_SEEN.clear()

