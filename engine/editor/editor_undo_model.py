from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class UndoEntry:
    label: str
    rev: int
    meta: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class UndoState:
    entries: tuple[UndoEntry, ...]
    cursor: int
    max_size: int


def push_entry(state: UndoState, entry: UndoEntry) -> UndoState:
    entries = list(state.entries)
    cursor = max(0, min(state.cursor, len(entries)))
    if cursor < len(entries):
        entries = entries[:cursor]
    entries.append(entry)
    if len(entries) > state.max_size:
        overflow = len(entries) - state.max_size
        entries = entries[overflow:]
        cursor = max(0, cursor - overflow)
    cursor = len(entries)
    return UndoState(entries=tuple(entries), cursor=cursor, max_size=state.max_size)


def can_undo(state: UndoState) -> bool:
    return bool(state.entries) and state.cursor > 0


def can_redo(state: UndoState) -> bool:
    return state.cursor < len(state.entries)


def undo_cursor(state: UndoState) -> UndoState:
    if not can_undo(state):
        return state
    return UndoState(entries=state.entries, cursor=state.cursor - 1, max_size=state.max_size)


def redo_cursor(state: UndoState) -> UndoState:
    if not can_redo(state):
        return state
    return UndoState(entries=state.entries, cursor=state.cursor + 1, max_size=state.max_size)


def compute_visible_history(state: UndoState, start: int, count: int) -> list[UndoEntry]:
    if count <= 0:
        return []
    safe_start = max(0, min(start, len(state.entries)))
    safe_end = max(safe_start, min(safe_start + count, len(state.entries)))
    return list(state.entries[safe_start:safe_end])
