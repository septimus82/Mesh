from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

MAX_RETAINED_FEEDBACK = 8
MAX_VISIBLE_FEEDBACK = 3
DUPLICATE_COLLAPSE_WINDOW_S = 1.0
FADE_OUT_WINDOW_S = 0.3


class FeedbackSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class FeedbackEntry:
    id: str
    message: str
    severity: FeedbackSeverity
    created_at: float
    expires_at: float | None
    sticky: bool
    count: int = 1


def default_ttl_for_severity(severity: FeedbackSeverity) -> float:
    if severity is FeedbackSeverity.WARNING:
        return 6.0
    if severity is FeedbackSeverity.ERROR:
        return 8.0
    return 4.0


def resolve_expiry(now: float, *, ttl: float | None, sticky: bool) -> float | None:
    if sticky:
        return None
    duration = float(ttl) if ttl is not None else 0.0
    if duration <= 0.0:
        duration = 0.1
    return float(now) + duration


def is_entry_expired(entry: FeedbackEntry, now: float) -> bool:
    expires_at = entry.expires_at
    if expires_at is None:
        return False
    return float(now) >= float(expires_at)


def filter_expired(entries: tuple[FeedbackEntry, ...], now: float) -> tuple[FeedbackEntry, ...]:
    return tuple(entry for entry in entries if not is_entry_expired(entry, now))


def find_collapsible_entry_index(
    entries: tuple[FeedbackEntry, ...],
    *,
    message: str,
    severity: FeedbackSeverity,
    now: float,
) -> int | None:
    for index in range(len(entries) - 1, -1, -1):
        entry = entries[index]
        if entry.message != message or entry.severity is not severity:
            continue
        if float(now) - float(entry.created_at) <= DUPLICATE_COLLAPSE_WINDOW_S:
            return index
        return None
    return None


def collapse_duplicate_entry(
    entry: FeedbackEntry,
    *,
    now: float,
    ttl: float | None,
    sticky: bool,
) -> FeedbackEntry:
    return replace(
        entry,
        created_at=float(now),
        expires_at=resolve_expiry(float(now), ttl=ttl, sticky=sticky),
        sticky=bool(sticky),
        count=int(entry.count) + 1,
    )


def select_overflow_index(entries: tuple[FeedbackEntry, ...]) -> int:
    for index, entry in enumerate(entries):
        if not entry.sticky:
            return index
    return 0


def append_with_overflow(
    entries: tuple[FeedbackEntry, ...],
    entry: FeedbackEntry,
    *,
    max_retained: int = MAX_RETAINED_FEEDBACK,
) -> tuple[FeedbackEntry, ...]:
    next_entries = list(entries)
    if len(next_entries) >= int(max_retained):
        del next_entries[select_overflow_index(entries)]
    next_entries.append(entry)
    return tuple(next_entries)


def visible_entries(
    entries: tuple[FeedbackEntry, ...],
    *,
    max_visible: int = MAX_VISIBLE_FEEDBACK,
) -> tuple[FeedbackEntry, ...]:
    if max_visible <= 0:
        return tuple()
    return tuple(entries[-int(max_visible) :])