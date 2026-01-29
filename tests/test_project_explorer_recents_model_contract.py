"""Contract tests for project explorer recents model."""

from __future__ import annotations

from engine.editor.project_explorer_model import (
    ProjectExplorerDisplayRow,
    ProjectExplorerRecentItem,
    ProjectRow,
    build_project_explorer_display_rows,
    clamp_selection_on_selectables,
    display_index_from_selectable_index,
    format_project_action_label,
    push_recent,
    selectable_index_from_display_index,
)


def test_push_recent_dedupes_and_limits() -> None:
    items = [
        ProjectExplorerRecentItem(kind="scene", rel_path="scenes/a.json", label="a.json"),
        ProjectExplorerRecentItem(kind="asset", rel_path="assets/a.png", label="a.png"),
    ]
    new_item = ProjectExplorerRecentItem(kind="scene", rel_path="scenes/a.json", label="a.json")
    updated = push_recent(items, new_item, limit=2)
    assert [item.rel_path for item in updated] == ["scenes/a.json", "assets/a.png"]


def test_display_rows_with_recents() -> None:
    rows = [
        ProjectRow(rel_path="assets", name="assets", depth=0, is_dir=True),
        ProjectRow(rel_path="assets/a.png", name="a.png", depth=1, is_dir=False),
    ]
    recents = [
        ProjectExplorerRecentItem(kind="scene", rel_path="scenes/demo.json", label="demo.json"),
    ]
    display_rows, selectable_rows = build_project_explorer_display_rows(rows, recents, "")
    assert display_rows[0].kind == "header"
    assert display_rows[0].header == "RECENT"
    assert display_rows[1].recent is not None
    assert any(row.header == "PROJECT" for row in display_rows if row.kind == "header")
    assert len(selectable_rows) == 4


def test_display_rows_without_recents() -> None:
    rows = [
        ProjectRow(rel_path="assets", name="assets", depth=0, is_dir=True),
    ]
    display_rows, selectable_rows = build_project_explorer_display_rows(rows, [], "")
    assert display_rows[0].kind == "header"
    assert display_rows[0].header == "RECENT"
    assert any(getattr(row, "action", None) == "clear_recents" for row in display_rows)
    assert len(selectable_rows) == 2


def test_selection_mapping_skips_headers() -> None:
    display_rows = [
        ProjectExplorerDisplayRow(kind="header", header="RECENT", entry=None, recent=None),
        ProjectExplorerDisplayRow(
            kind="entry",
            header=None,
            entry=None,
            recent=ProjectExplorerRecentItem(kind="scene", rel_path="scenes/a.json", label="a.json"),
        ),
        ProjectExplorerDisplayRow(kind="header", header="PROJECT", entry=None, recent=None),
        ProjectExplorerDisplayRow(
            kind="entry",
            header=None,
            entry=ProjectRow(rel_path="assets/a.png", name="a.png", depth=0, is_dir=False),
            recent=None,
        ),
    ]
    assert display_index_from_selectable_index(display_rows, 0) == 1
    assert display_index_from_selectable_index(display_rows, 1) == 3
    assert selectable_index_from_display_index(display_rows, 0) is None
    assert selectable_index_from_display_index(display_rows, 1) == 0
    assert selectable_index_from_display_index(display_rows, 3) == 1
    assert clamp_selection_on_selectables(-1, 0) == -1
    assert clamp_selection_on_selectables(5, 2) == 1


def test_clear_recents_label_has_shortcut_hint() -> None:
    row = ProjectExplorerDisplayRow(
        kind="action", header=None, entry=None, recent=None, action="clear_recents"
    )
    assert format_project_action_label(row) == "Clear recents (Del)"
