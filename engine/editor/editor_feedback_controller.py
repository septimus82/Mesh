from __future__ import annotations

import time
from typing import Any, Callable

from .editor_feedback_model import (
    FeedbackEntry,
    FeedbackSeverity,
    append_with_overflow,
    collapse_duplicate_entry,
    default_ttl_for_severity,
    filter_expired,
    find_collapsible_entry_index,
    resolve_expiry,
)


class EditorFeedbackController:
    def __init__(self, editor: Any, *, clock: Callable[[], float] | None = None) -> None:
        self._editor = editor
        self._clock = clock or time.monotonic
        self._entries: tuple[FeedbackEntry, ...] = tuple()
        self._counter = 0

    def info(self, message: str, *, ttl: float = 4.0) -> None:
        self.toast(message, FeedbackSeverity.INFO, ttl=ttl)

    def warning(self, message: str, *, ttl: float = 6.0) -> None:
        self.toast(message, FeedbackSeverity.WARNING, ttl=ttl)

    def error(self, message: str, *, ttl: float = 8.0, sticky: bool = False) -> None:
        self.toast(message, FeedbackSeverity.ERROR, ttl=ttl, sticky=sticky)

    def toast(
        self,
        message: str,
        severity: FeedbackSeverity = FeedbackSeverity.INFO,
        *,
        ttl: float | None = None,
        sticky: bool = False,
    ) -> None:
        text = str(message or "").strip()
        if not text:
            return
        now = float(self._clock())
        self.tick(now)
        resolved_ttl = default_ttl_for_severity(severity) if ttl is None else float(ttl)
        collapse_index = find_collapsible_entry_index(
            self._entries,
            message=text,
            severity=severity,
            now=now,
        )
        if collapse_index is not None:
            updated = collapse_duplicate_entry(
                self._entries[collapse_index],
                now=now,
                ttl=resolved_ttl,
                sticky=sticky,
            )
            entries = list(self._entries)
            entries[collapse_index] = updated
            self._entries = tuple(entries)
            return

        self._counter += 1
        entry = FeedbackEntry(
            id=f"fb-{self._counter}",
            message=text,
            severity=severity,
            created_at=now,
            expires_at=resolve_expiry(now, ttl=resolved_ttl, sticky=sticky),
            sticky=bool(sticky),
        )
        self._entries = append_with_overflow(self._entries, entry)

    def clear(self) -> None:
        self._entries = tuple()

    def pending(self) -> tuple[FeedbackEntry, ...]:
        self.tick()
        return self._entries

    def dismiss(self, entry_id: str) -> bool:
        target_id = str(entry_id or "").strip()
        if not target_id:
            return False
        kept = tuple(entry for entry in self._entries if entry.id != target_id)
        if len(kept) == len(self._entries):
            return False
        self._entries = kept
        return True

    def tick(self, now: float | None = None) -> None:
        current = float(self._clock()) if now is None else float(now)
        self._entries = filter_expired(self._entries, current)