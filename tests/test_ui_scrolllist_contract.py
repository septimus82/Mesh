from __future__ import annotations

import pytest

from engine.ui_overlays.widgets import Rect, ScrollList

pytestmark = [pytest.mark.fast]


def _row_signature(rows: list[tuple[int, str, Rect, bool]]) -> list[tuple[int, str, float, float, bool]]:
    return [
        (idx, text, round(rect.y, 3), round(rect.height, 3), selected)
        for idx, text, rect, selected in rows
    ]


def test_scrolllist_visible_layout_is_deterministic() -> None:
    widget = ScrollList(
        items=[f"item-{i}" for i in range(8)],
        row_height=20,
        selected_index=2,
        scroll_offset=1.0,
    )
    bounds = Rect(x=10.0, y=50.0, width=200.0, height=80.0)
    first = widget.layout(bounds)
    first_rows = _row_signature(widget.visible_rows)
    second = widget.layout(bounds)
    second_rows = _row_signature(widget.visible_rows)
    assert first_rows == second_rows
    assert first.instructions == second.instructions
    assert [row[0] for row in widget.visible_rows] == [1, 2, 3, 4]


def test_scrolllist_scroll_clamps() -> None:
    widget = ScrollList(
        items=[str(i) for i in range(12)],
        row_height=10,
        selected_index=0,
        scroll_offset=0.0,
    )
    widget.layout(Rect(x=0.0, y=0.0, width=100.0, height=30.0))  # 3 visible
    changed = widget.on_mouse_wheel(-50.0)
    assert changed is True
    assert widget.scroll_offset == pytest.approx(9.0)  # max 12-3
    changed_again = widget.on_mouse_wheel(100.0)
    assert changed_again is True
    assert widget.scroll_offset == pytest.approx(0.0)


def test_scrolllist_click_selects_correct_row() -> None:
    widget = ScrollList(
        items=["a", "b", "c", "d"],
        row_height=20,
        selected_index=0,
        scroll_offset=0.0,
    )
    widget.layout(Rect(x=0.0, y=0.0, width=100.0, height=80.0))
    assert widget.on_mouse_press(50.0, 45.0) is True  # second row
    assert widget.selected_index == 1


def test_scrolllist_ensure_visible_moves_window_deterministically() -> None:
    widget = ScrollList(
        items=[f"row-{i}" for i in range(20)],
        row_height=10,
        selected_index=0,
        scroll_offset=0.0,
    )
    bounds = Rect(x=0.0, y=0.0, width=120.0, height=40.0)  # 4 rows visible
    widget.layout(bounds)

    assert widget.ensure_visible(7) is True
    assert widget.selected_index == 7
    assert widget.scroll_offset == pytest.approx(4.0)
    assert [idx for idx, _text, _rect, _sel in widget.visible_rows] == [4, 5, 6, 7]


def test_scrolllist_page_home_end_keyboard_navigation() -> None:
    widget = ScrollList(
        items=[f"row-{i}" for i in range(30)],
        row_height=10,
        selected_index=0,
        scroll_offset=0.0,
    )
    bounds = Rect(x=0.0, y=0.0, width=150.0, height=50.0)  # 5 rows visible
    widget.layout(bounds)

    assert widget.on_key_page_down() is True
    assert widget.selected_index == 5
    assert widget.scroll_offset == pytest.approx(1.0)

    assert widget.on_key_page_up() is True
    assert widget.selected_index == 0
    assert widget.scroll_offset == pytest.approx(0.0)

    assert widget.on_key_end() is True
    assert widget.selected_index == 29
    assert widget.scroll_offset == pytest.approx(25.0)

    assert widget.on_key_home() is True
    assert widget.selected_index == 0
    assert widget.scroll_offset == pytest.approx(0.0)
