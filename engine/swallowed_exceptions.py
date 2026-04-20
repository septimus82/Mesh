from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass

from engine.logging_tools import get_logger

_LOCK = threading.Lock()


@dataclass(frozen=True)
class SwallowedSiteStats:
    count: int
    first_seen_ts: float
    last_seen_ts: float


_SITES: dict[str, SwallowedSiteStats] = {}
_LAST_LOG_TS: dict[str, float] = {}
_LOG_SAMPLE_SECONDS = 60.0
_SWALLOW_ONCE_TAGS: set[str] = set()
_LOGGER = get_logger(__name__)


def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    # Bridge: record every call inside an active except into the telemetry
    # counter. This runs before the once-gate so count tracking is not
    # suppressed by log-once behavior.
    exc = sys.exc_info()[1]
    if exc is not None:
        record_swallowed(tag, exc)
    if once:
        with _LOCK:
            if tag in _SWALLOW_ONCE_TAGS:
                return
            _SWALLOW_ONCE_TAGS.add(tag)
    _LOGGER.debug("SWALLOW[%s] %s", tag, context, exc_info=True)


def record_swallowed(site: str, exc: Exception) -> None:
    """Record a swallowed exception site for diagnostics/guard rails."""
    key = str(site or "<unknown>")
    now = time.time()
    with _LOCK:
        previous = _SITES.get(key)
        if previous is None:
            _SITES[key] = SwallowedSiteStats(count=1, first_seen_ts=now, last_seen_ts=now)
            return
        _SITES[key] = SwallowedSiteStats(
            count=previous.count + 1,
            first_seen_ts=previous.first_seen_ts,
            last_seen_ts=now,
        )


def should_log(site: str, sample_seconds: float = _LOG_SAMPLE_SECONDS) -> bool:
    key = str(site or "<unknown>")
    now = time.time()
    with _LOCK:
        last = _LAST_LOG_TS.get(key)
        if last is None or now - last >= sample_seconds:
            _LAST_LOG_TS[key] = now
            return True
        return False


def read_counts() -> dict[str, int]:
    with _LOCK:
        return {site: stats.count for site, stats in _SITES.items()}


def read_sites() -> dict[str, SwallowedSiteStats]:
    with _LOCK:
        return dict(_SITES)


def get_and_reset_counts() -> dict[str, int]:
    with _LOCK:
        snapshot = {site: stats.count for site, stats in _SITES.items()}
        _SITES.clear()
        _LAST_LOG_TS.clear()
    return snapshot


def reset() -> None:
    with _LOCK:
        _SITES.clear()
        _LAST_LOG_TS.clear()
        _SWALLOW_ONCE_TAGS.clear()


def format_swallowed_summary(limit: int = 20) -> str:
    with _LOCK:
        rows = sorted(_SITES.items(), key=lambda item: (-item[1].count, item[0]))
    if limit >= 0:
        rows = rows[:limit]
    if not rows:
        return "no swallowed exceptions recorded"
    lines = ["swallowed_exceptions summary:"]
    for site, stats in rows:
        lines.append(
            f"{site}: count={stats.count} first={stats.first_seen_ts:.3f} last={stats.last_seen_ts:.3f}"
        )
    return "\n".join(lines)
