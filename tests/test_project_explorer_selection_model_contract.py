"""Contract tests for project_explorer_selection_model."""
from __future__ import annotations

from engine.editor.project_explorer_selection_model import (
    SelectionState,
    clear_selection,
    move_primary,
    select_all,
    select_range,
    select_single,
    selected_indices_sorted,
    selection_summary,
    toggle_index,
)


def test_select_single_sets_primary_and_anchor() -> None:
    state = SelectionState(primary_index=0, selected_indices=frozenset(), anchor_index=None)
    next_state = select_single(state, 3)
    assert next_state.primary_index == 3
    assert next_state.selected_indices == frozenset({3})
    assert next_state.anchor_index == 3


def test_toggle_index_adds_and_removes() -> None:
    state = SelectionState(primary_index=1, selected_indices=frozenset({1}), anchor_index=1)
    next_state = toggle_index(state, 2)
    assert next_state.selected_indices == frozenset({1, 2})
    assert next_state.primary_index == 2

    next_state2 = toggle_index(next_state, 2)
    assert next_state2.selected_indices == frozenset({1})
    assert next_state2.primary_index == 1


def test_select_range_uses_anchor() -> None:
    state = SelectionState(primary_index=2, selected_indices=frozenset({2}), anchor_index=2)
    next_state = select_range(state, 5)
    assert next_state.selected_indices == frozenset({2, 3, 4, 5})
    assert next_state.primary_index == 5
    assert next_state.anchor_index == 2


def test_select_range_sets_anchor_if_missing() -> None:
    state = SelectionState(primary_index=3, selected_indices=frozenset({3}), anchor_index=None)
    next_state = select_range(state, 1)
    assert next_state.selected_indices == frozenset({1, 2, 3})
    assert next_state.anchor_index == 3


def test_move_primary_extend_and_collapse() -> None:
    state = SelectionState(primary_index=2, selected_indices=frozenset({2}), anchor_index=2)
    next_state = move_primary(state, 1, extend=False)
    assert next_state.selected_indices == frozenset({3})
    assert next_state.primary_index == 3

    next_state2 = move_primary(state, 2, extend=True)
    assert next_state2.selected_indices == frozenset({2, 3, 4})
    assert next_state2.primary_index == 4


def test_selected_indices_sorted() -> None:
    state = SelectionState(primary_index=2, selected_indices=frozenset({5, 1, 2}), anchor_index=2)
    assert selected_indices_sorted(state) == (1, 2, 5)


def test_selection_summary() -> None:
    state = SelectionState(primary_index=2, selected_indices=frozenset({2, 3}), anchor_index=2)
    summary = selection_summary(state)
    assert summary["count"] == 2
    assert summary["primary"] == 2
    assert summary["has_multi"] is True


def test_select_all_and_clear_selection() -> None:
    state = SelectionState(primary_index=5, selected_indices=frozenset({5}), anchor_index=5)
    next_state = select_all(state, 3)
    assert next_state.selected_indices == frozenset({0, 1, 2})
    assert next_state.primary_index == 2

    cleared = clear_selection(next_state)
    assert cleared.selected_indices == frozenset()
