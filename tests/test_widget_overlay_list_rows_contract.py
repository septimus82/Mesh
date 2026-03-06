from __future__ import annotations

import pytest

from engine.ui_overlays.widget_overlay_helpers import (
    build_empty_row,
    build_status_row,
    compose_list_rows,
    resolve_preserved_selection_index,
)

pytestmark = [pytest.mark.fast]


def test_build_empty_row_is_deterministic() -> None:
    message = "(No matches)"
    assert build_empty_row(message) == "(No matches)"
    assert build_empty_row(message) == "(No matches)"


def test_build_status_row_zero_count_stable() -> None:
    assert build_status_row(count=0, selected_index=0) == "Results: 0"
    assert build_status_row(count=-4, selected_index=12) == "Results: 0"


def test_build_status_row_selection_formatting() -> None:
    assert build_status_row(count=3, selected_index=1) == "Results: 3  Selected: 2/3"
    assert build_status_row(count=3, selected_index=-20) == "Results: 3  Selected: 1/3"
    assert build_status_row(count=3, selected_index=20) == "Results: 3  Selected: 3/3"


def test_build_status_row_no_selection_and_custom_label() -> None:
    assert build_status_row(count=3, selected_index=None) == "Results: 3"
    assert build_status_row(label="Items", count=2, selected_index=0) == "Items: 2  Selected: 1/2"


def test_compose_list_rows_with_content_and_status_is_deterministic() -> None:
    base = ["row-1", "row-2"]
    out = compose_list_rows(base, empty_row="(empty)", status_row="Results: 2  Selected: 1/2", show_status=True)
    assert out == ["row-1", "row-2", "Results: 2  Selected: 1/2"]
    assert base == ["row-1", "row-2"]


def test_compose_list_rows_empty_and_status_behavior() -> None:
    assert compose_list_rows([], empty_row="(No matches)", status_row="Results: 0", show_status=True) == [
        "(No matches)",
        "Results: 0",
    ]
    assert compose_list_rows([], empty_row="(No matches)", status_row="Results: 0", show_status=False) == [
        "(No matches)",
    ]


def test_compose_list_rows_hints_row_is_appended_deterministically() -> None:
    assert compose_list_rows(
        ["row-1"],
        empty_row="(No matches)",
        status_row="Results: 1  Selected: 1/1",
        hints_row="Hints: Tab focus",
        show_status=True,
    ) == [
        "row-1",
        "Results: 1  Selected: 1/1",
        "Hints: Tab focus",
    ]
    assert compose_list_rows(
        [],
        empty_row="(No matches)",
        status_row="Results: 0",
        hints_row="Hints: Tab focus",
        show_status=False,
    ) == [
        "(No matches)",
        "Hints: Tab focus",
    ]


def _identity(item: dict[str, str]) -> str | None:
    return item.get("id")


def _clamp(index: int, count: int) -> int:
    if count <= 0:
        return -1
    return max(0, min(int(index), count - 1))


def test_resolve_preserved_selection_index_preserves_when_identity_remains() -> None:
    previous = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    new = [{"id": "x"}, {"id": "b"}]
    selected, preserved = resolve_preserved_selection_index(
        previous,
        new,
        1,
        identity_fn=_identity,
        clamp_fn=_clamp,
        fallback_index=0,
    )
    assert preserved is True
    assert selected == 1


def test_resolve_preserved_selection_index_falls_back_deterministically_when_missing() -> None:
    previous = [{"id": "a"}, {"id": "b"}]
    new = [{"id": "x"}, {"id": "y"}]
    selected, preserved = resolve_preserved_selection_index(
        previous,
        new,
        1,
        identity_fn=_identity,
        clamp_fn=_clamp,
        fallback_index=0,
    )
    assert preserved is False
    assert selected == 0


def test_resolve_preserved_selection_index_handles_empty_and_invalid_previous_index() -> None:
    selected, preserved = resolve_preserved_selection_index(
        [{"id": "a"}],
        [],
        99,
        identity_fn=_identity,
        clamp_fn=_clamp,
        fallback_index=0,
    )
    assert preserved is False
    assert selected == -1


def test_resolve_preserved_selection_index_duplicate_identity_uses_first_match() -> None:
    previous = [{"id": "keep"}]
    new = [{"id": "keep"}, {"id": "keep"}]
    selected, preserved = resolve_preserved_selection_index(
        previous,
        new,
        0,
        identity_fn=_identity,
        clamp_fn=_clamp,
        fallback_index=0,
    )
    assert preserved is True
    assert selected == 0
