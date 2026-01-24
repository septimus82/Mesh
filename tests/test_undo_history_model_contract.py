"""Contract tests for undo_history_model."""

from __future__ import annotations

from engine.editor.undo_history_model import (
    UndoEntry,
    build_undo_history_entries,
    clamp_history_cursor,
    compute_history_window,
    resolve_jump_delta,
)


def test_build_entries_with_current_marker() -> None:
    undo_stack = [
        {"type": "MoveEntity"},
        {"type": "RotateEntities"},
    ]
    redo_stack = [
        {"type": "EditLight"},
    ]

    entries = build_undo_history_entries(undo_stack, redo_stack)
    assert [e.label for e in entries] == ["LIGHT", "ROTATE", "MOVE"]
    assert [e.index for e in entries] == [1, 2, 3]
    assert [e.real_index for e in entries] == [0, 1, 2]
    assert entries[1].is_current is True


def test_clamp_history_cursor() -> None:
    assert clamp_history_cursor(0, 0) == -1
    assert clamp_history_cursor(-5, 3) == 0
    assert clamp_history_cursor(10, 3) == 2


def test_compute_history_window() -> None:
    start, visible = compute_history_window(0, 10, 4)
    assert (start, visible) == (0, 4)

    start, visible = compute_history_window(5, 10, 4)
    assert (start, visible) == (3, 4)


def test_resolve_jump_delta() -> None:
    entries = [
        UndoEntry(index=1, real_index=0, label="A", is_current=False),
        UndoEntry(index=2, real_index=1, label="B", is_current=True),
        UndoEntry(index=3, real_index=2, label="C", is_current=False),
    ]
    assert resolve_jump_delta(entries, 0) == 1
    assert resolve_jump_delta(entries, 2) == -1
    assert resolve_jump_delta(entries, 1) == 0


def test_resolve_jump_delta_without_current() -> None:
    entries = [
        UndoEntry(index=1, real_index=0, label="A", is_current=False),
        UndoEntry(index=2, real_index=1, label="B", is_current=False),
        UndoEntry(index=3, real_index=2, label="C", is_current=False),
    ]
    assert resolve_jump_delta(entries, 0) == 3
    assert resolve_jump_delta(entries, 2) == 1


def test_label_mapping_and_fallback() -> None:
    entries = build_undo_history_entries(
        [{"type": "ScaleEntities"}, {"type": "AltDragDuplicate"}],
        [{"type": "UnknownType"}],
    )
    assert entries[0].label == "CMD:UnknownType"
    assert entries[1].label == "ALT-DUP"
    assert entries[2].label == "SCALE"
