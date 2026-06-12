"""Contract tests for find_everything_model."""

from __future__ import annotations

from engine.editor.find_everything_model import (
    FindItem,
    FindResult,
    build_find_display_rows,
    build_find_everything_hint_line,
    build_find_groups,
    clamp_selection,
    compute_find_counts,
    filter_find_items,
    move_selection,
)


def test_filter_find_items_deterministic_order() -> None:
    items = [
        FindItem(kind="command", item_id="cmd.save", title="Save Scene", subtitle="", keywords=("save",)),
        FindItem(kind="scene", item_id="scn.1", title="Ridge Outpost", subtitle="packs/core_regions/scenes/...", keywords=()),
        FindItem(kind="entity", item_id="player", title="player", subtitle="Player", keywords=("player",)),
    ]
    results = filter_find_items(items, "", limit=10)
    assert [r.title for r in results] == [
        "Command: Save Scene",
        "Scene: Ridge Outpost",
        "Entity: player",
    ]


def test_filter_find_items_query_scores_title_first() -> None:
    items = [
        FindItem(kind="scene", item_id="scn.1", title="Save Haven", subtitle="", keywords=()),
        FindItem(kind="command", item_id="cmd.save", title="Save Scene", subtitle="", keywords=("save",)),
    ]
    results = filter_find_items(items, "save", limit=10)
    titles = [r.title for r in results]
    assert "Command: Save Scene" in titles


def test_filter_find_items_limit() -> None:
    items = [
        FindItem(kind="command", item_id=f"cmd.{i}", title=f"Cmd {i}", subtitle="", keywords=())
        for i in range(20)
    ]
    results = filter_find_items(items, "", limit=10)
    assert len(results) == 10


def test_selection_clamp_and_move_wrap() -> None:
    assert clamp_selection(0, 0) == -1
    assert clamp_selection(-2, 3) == 0
    assert clamp_selection(5, 3) == 2
    assert move_selection(0, 1, 3) == 1
    assert move_selection(2, 1, 3) == 0


def test_build_groups_and_counts() -> None:
    rows = [
        FindResult(kind="scene", item_id="s1", title="Scene: One", subtitle=""),
        FindResult(kind="entity", item_id="e1", title="Entity: Hero", subtitle=""),
        FindResult(kind="scene", item_id="s2", title="Scene: Two", subtitle=""),
    ]
    groups = build_find_groups(rows)
    assert [group.name for group in groups] == ["Scenes", "Entities"]
    assert [len(group.rows) for group in groups] == [2, 1]

    counts = compute_find_counts(rows, include_zero=True)
    assert counts["total"] == 3
    by_group = counts["by_group"]
    assert by_group["Scenes"] == 2
    assert by_group["Entities"] == 1
    assert by_group["Assets"] == 0


def test_build_display_rows_headers_and_footer() -> None:
    rows = [
        FindResult(kind="scene", item_id="s1", title="Scene: One", subtitle=""),
        FindResult(kind="asset", item_id="a1", title="Asset: a.png", subtitle="image"),
    ]
    counts = compute_find_counts(rows, include_zero=True)
    display = build_find_display_rows(rows, counts)
    texts = [row.text for row in display]
    assert texts[0].startswith("SCENES (")
    assert "ASSETS" in " ".join(texts)
    assert "results" in texts[-1]
    row_indices = [row.row_index for row in display if row.kind == "row"]
    assert row_indices == [0, 1]


def test_hint_line_keyboard_gamepad_ascii() -> None:
    keyboard = build_find_everything_hint_line("keyboard_mouse")
    gamepad = build_find_everything_hint_line("gamepad")
    assert keyboard == "Enter: Open   Esc: Close   Up/Down: Navigate"
    assert gamepad == "A: Open   B: Close   D-pad: Navigate"
    assert keyboard.isascii()
    assert gamepad.isascii()
