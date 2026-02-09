from __future__ import annotations

from engine.editor.editor_undo_model import (
    UndoEntry,
    UndoState,
    can_redo,
    can_undo,
    compute_visible_history,
    push_entry,
    redo_cursor,
    undo_cursor,
)


def test_push_truncates_and_clears_redo() -> None:
    state = UndoState(entries=tuple(), cursor=0, max_size=2)
    state = push_entry(state, UndoEntry(label="A", rev=1))
    state = push_entry(state, UndoEntry(label="B", rev=2))
    state = undo_cursor(state)
    state = push_entry(state, UndoEntry(label="C", rev=3))
    labels = [entry.label for entry in state.entries]
    assert labels == ["A", "C"]
    assert state.cursor == 2


def test_can_undo_redo_and_cursor_moves() -> None:
    state = UndoState(entries=(UndoEntry(label="A", rev=1), UndoEntry(label="B", rev=2)), cursor=2, max_size=4)
    assert can_undo(state) is True
    assert can_redo(state) is False
    state = undo_cursor(state)
    assert state.cursor == 1
    assert can_redo(state) is True
    state = redo_cursor(state)
    assert state.cursor == 2


def test_compute_visible_history_stable_slice() -> None:
    entries = tuple(UndoEntry(label=f"E{i}", rev=i) for i in range(5))
    state = UndoState(entries=entries, cursor=5, max_size=10)
    visible = compute_visible_history(state, start=1, count=2)
    assert [entry.label for entry in visible] == ["E1", "E2"]
