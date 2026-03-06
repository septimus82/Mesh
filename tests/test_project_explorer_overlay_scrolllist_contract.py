from __future__ import annotations

import pytest

from engine.editor.project_explorer.project_explorer_model import (
    ProjectExplorerDisplayRow,
    ProjectRow,
)
from engine.ui.widgets import Rect
from engine.ui_overlays.project_explorer_overlay import (
    _build_project_explorer_scrolllist,
    _selected_project_row_from_scrolllist,
)

pytestmark = [pytest.mark.fast]


def _make_rows(count: int) -> list[ProjectExplorerDisplayRow]:
    rows: list[ProjectExplorerDisplayRow] = []
    for i in range(count):
        entry = ProjectRow(
            rel_path=f"assets/item_{i}.png",
            name=f"item_{i}.png",
            depth=0,
            is_dir=False,
        )
        rows.append(
            ProjectExplorerDisplayRow(
                kind="entry",
                header=None,
                entry=entry,
                recent=None,
            )
        )
    return rows


def _fmt_action(row: ProjectExplorerDisplayRow) -> str:
    return "action" if row.action else ""


def _fmt_recent(recent: object) -> str:
    return f"recent:{getattr(recent, 'label', '')}"


def _fmt_row(entry: ProjectRow) -> str:
    return entry.name


def _visible_signature(scroll_list) -> list[tuple[int, str, tuple[float, float, float, float], bool]]:
    rows: list[tuple[int, str, tuple[float, float, float, float], bool]] = []
    for row_idx, text, rect, selected in scroll_list.visible_rows:
        rows.append((row_idx, text, (rect.x, rect.y, rect.width, rect.height), selected))
    return rows


def test_project_explorer_scrolllist_visible_rows_deterministic() -> None:
    rows = _make_rows(12)
    rect = Rect(x=10.0, y=20.0, width=300.0, height=90.0)
    first = _build_project_explorer_scrolllist(
        rows=rows,
        panel_list_rect=rect,
        row_height=18.0,
        start_index=0,
        scroll_y=0.0,
        selected_row_id=id(rows[0]),
        format_project_action_label=_fmt_action,
        format_project_recent_label=_fmt_recent,
        format_project_row_label=_fmt_row,
    )
    second = _build_project_explorer_scrolllist(
        rows=rows,
        panel_list_rect=rect,
        row_height=18.0,
        start_index=0,
        scroll_y=0.0,
        selected_row_id=id(rows[0]),
        format_project_action_label=_fmt_action,
        format_project_recent_label=_fmt_recent,
        format_project_row_label=_fmt_row,
    )
    assert _visible_signature(first) == _visible_signature(second)
    assert [row[0] for row in first.visible_rows] == [0, 1, 2, 3, 4]


def test_project_explorer_scrolllist_wheel_and_click_selection() -> None:
    rows = _make_rows(12)
    rect = Rect(x=10.0, y=20.0, width=300.0, height=90.0)
    scroll_list = _build_project_explorer_scrolllist(
        rows=rows,
        panel_list_rect=rect,
        row_height=18.0,
        start_index=0,
        scroll_y=0.0,
        selected_row_id=id(rows[0]),
        format_project_action_label=_fmt_action,
        format_project_recent_label=_fmt_recent,
        format_project_row_label=_fmt_row,
    )

    changed = scroll_list.on_mouse_wheel(-2.0)
    assert changed is True
    assert scroll_list.scroll_offset == pytest.approx(2.0)
    assert [row[0] for row in scroll_list.visible_rows] == [2, 3, 4, 5, 6]

    row_index, _text, row_rect, _selected = scroll_list.visible_rows[2]
    handled = scroll_list.on_mouse_press(row_rect.left + 3.0, row_rect.center_y)
    assert handled is True
    selected_row = _selected_project_row_from_scrolllist(rows, scroll_list)
    assert selected_row is rows[row_index]

