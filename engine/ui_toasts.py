from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(slots=True)
class ToastEntry:
    message: str
    ttl_s: float
    created_t: float


@dataclass(slots=True)
class ToastManager:
    _time_s: float = 0.0
    _toasts: List[ToastEntry] = field(default_factory=list)
    _fade_window_s: float = 0.5

    def push_toast(self, message: str, ttl_s: float = 2.5) -> None:
        text = str(message or "").strip()
        if not text:
            return
        duration = float(ttl_s)
        if duration <= 0.0:
            duration = 0.1
        self._toasts.append(ToastEntry(text, duration, self._time_s))

    def tick(self, dt: float) -> None:
        self._time_s += max(0.0, float(dt))
        if not self._toasts:
            return
        now = self._time_s
        self._toasts = [t for t in self._toasts if (now - t.created_t) < t.ttl_s]

    def clear(self) -> None:
        self._toasts.clear()

    def get_active_toasts(self) -> list[str]:
        return [t.message for t in self._toasts]

    def get_active_entries(self) -> list[tuple[str, float]]:
        entries: list[tuple[str, float]] = []
        for toast in self._toasts:
            entries.append((toast.message, self._fade_alpha(toast)))
        return entries

    def _fade_alpha(self, toast: ToastEntry) -> float:
        if self._fade_window_s <= 0.0:
            return 1.0
        age = self._time_s - toast.created_t
        remaining = toast.ttl_s - age
        if remaining <= 0.0:
            return 0.0
        if remaining >= self._fade_window_s:
            return 1.0
        return max(0.0, remaining / self._fade_window_s)
