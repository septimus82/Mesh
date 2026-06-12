"""Pure selection model for Project Explorer multi-select."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, Tuple

__all__ = [
    "SelectionState",
    "select_single",
    "toggle_index",
    "select_range",
    "select_all",
    "clear_selection",
    "move_primary",
    "selected_indices_sorted",
    "selection_summary",
]


@dataclass(frozen=True, slots=True)
class SelectionState:
    primary_index: int
    selected_indices: FrozenSet[int]
    anchor_index: int | None


def _clamp_non_negative(index: int) -> int:
    return max(0, int(index))


def select_single(state: SelectionState, idx: int) -> SelectionState:
    idx = _clamp_non_negative(idx)
    return SelectionState(
        primary_index=idx,
        selected_indices=frozenset({idx}),
        anchor_index=idx,
    )


def toggle_index(state: SelectionState, idx: int) -> SelectionState:
    idx = _clamp_non_negative(idx)
    selected = set(state.selected_indices)
    if idx in selected:
        if len(selected) > 1:
            selected.remove(idx)
            primary = state.primary_index
            if primary == idx:
                primary = min(selected) if selected else idx
            if primary not in selected and selected:
                selected.add(primary)
            return SelectionState(
                primary_index=primary,
                selected_indices=frozenset(selected),
                anchor_index=state.anchor_index,
            )
        return state

    selected.add(idx)
    return SelectionState(
        primary_index=idx,
        selected_indices=frozenset(selected),
        anchor_index=state.anchor_index if state.anchor_index is not None else idx,
    )


def select_range(state: SelectionState, idx: int) -> SelectionState:
    idx = _clamp_non_negative(idx)
    anchor = state.anchor_index if state.anchor_index is not None else state.primary_index
    start = min(anchor, idx)
    end = max(anchor, idx)
    return SelectionState(
        primary_index=idx,
        selected_indices=frozenset(range(start, end + 1)),
        anchor_index=anchor,
    )


def select_all(state: SelectionState, count: int) -> SelectionState:
    count = max(0, int(count))
    if count == 0:
        return clear_selection(state)
    indices = frozenset(range(count))
    primary = state.primary_index
    if primary < 0 or primary >= count:
        primary = count - 1
    anchor = state.anchor_index if state.anchor_index is not None else primary
    return SelectionState(
        primary_index=primary,
        selected_indices=indices,
        anchor_index=anchor,
    )


def clear_selection(state: SelectionState) -> SelectionState:
    return SelectionState(
        primary_index=-1,
        selected_indices=frozenset(),
        anchor_index=state.anchor_index,
    )


def move_primary(state: SelectionState, delta: int, extend: bool) -> SelectionState:
    new_index = _clamp_non_negative(state.primary_index + int(delta))
    if extend:
        anchor = state.anchor_index if state.anchor_index is not None else state.primary_index
        start = min(anchor, new_index)
        end = max(anchor, new_index)
        return SelectionState(
            primary_index=new_index,
            selected_indices=frozenset(range(start, end + 1)),
            anchor_index=anchor,
        )
    return SelectionState(
        primary_index=new_index,
        selected_indices=frozenset({new_index}),
        anchor_index=new_index,
    )


def selected_indices_sorted(state: SelectionState) -> Tuple[int, ...]:
    return tuple(sorted(state.selected_indices))


def selection_summary(state: SelectionState) -> Dict[str, int | bool]:
    count = len(state.selected_indices)
    return {
        "count": count,
        "primary": state.primary_index,
        "has_multi": count > 1,
    }
