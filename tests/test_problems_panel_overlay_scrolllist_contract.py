from __future__ import annotations

import pytest

from engine.editor.scene_lint_model import SceneLintIssue
from engine.ui.widgets import Rect
from engine.ui_overlays.problems_panel_overlay import _build_problems_rows_scrolllist

pytestmark = [pytest.mark.fast]


def _issue(i: int) -> SceneLintIssue:
    return SceneLintIssue(
        issue_id=f"issue_{i}",
        kind="DUPLICATE_ID",
        message=f"Problem {i}",
        entity_id=f"entity_{i}",
        scene_id="scenes/test.json",
        severity="WARN",
        risk="safe",
        fix_kind="rename_id",
        fixable=True,
        meta={"index": i},
    )


def _visible_signature(rows: list[tuple[int, str, Rect, bool]]) -> list[tuple[int, str, tuple[float, float, float, float], bool]]:
    return [
        (idx, text, (rect.x, rect.y, rect.width, rect.height), selected)
        for idx, text, rect, selected in rows
    ]


def test_problems_panel_scrolllist_visible_rows_deterministic() -> None:
    issues = [_issue(i) for i in range(12)]
    rect = Rect(x=10.0, y=20.0, width=320.0, height=90.0)

    first = _build_problems_rows_scrolllist(issues, rect, row_height=18)
    second = _build_problems_rows_scrolllist(issues, rect, row_height=18)

    first_sig = _visible_signature(first.visible_rows)
    second_sig = _visible_signature(second.visible_rows)
    assert first_sig == second_sig
    assert [row[0] for row in first.visible_rows] == [0, 1, 2, 3, 4]
    assert "Problem 0" in first.visible_rows[0][1]


def test_problems_panel_scrolllist_wheel_and_click_selection() -> None:
    issues = [_issue(i) for i in range(12)]
    rect = Rect(x=10.0, y=20.0, width=320.0, height=90.0)
    scroll = _build_problems_rows_scrolllist(issues, rect, row_height=18)

    changed = scroll.on_mouse_wheel(-2.0)
    assert changed is True
    assert scroll.scroll_offset == pytest.approx(2.0)
    assert [row[0] for row in scroll.visible_rows] == [2, 3, 4, 5, 6]

    row_index, _text, row_rect, _sel = scroll.visible_rows[2]
    handled = scroll.on_mouse_press(row_rect.left + 4.0, row_rect.center_y)
    assert handled is True
    assert scroll.selected_index == row_index

