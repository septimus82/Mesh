from __future__ import annotations


def test_scene_dirty_overlay_shows_undo_redo_counts() -> None:
    from engine.ui import format_scene_dirty_overlay_lines

    assert format_scene_dirty_overlay_lines({"enabled": True, "dirty": False, "undo": 3, "redo": 1}) == [
        "SCENE CLEAN",
        "undo=3 redo=1",
    ]
    assert format_scene_dirty_overlay_lines({"enabled": True, "dirty": True, "reason": "undo", "counter": 9, "undo": 4, "redo": 0}) == [
        "SCENE DIRTY reason=undo rev=9",
        "undo=4 redo=0",
    ]

