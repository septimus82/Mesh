from __future__ import annotations


def test_scene_dirty_overlay_formatting() -> None:
    from engine.ui import format_scene_dirty_overlay_lines

    assert format_scene_dirty_overlay_lines({"enabled": False}) == []
    assert format_scene_dirty_overlay_lines({"enabled": True, "dirty": False}) == ["SCENE CLEAN", "undo=0 redo=0"]
    assert format_scene_dirty_overlay_lines({"enabled": True, "dirty": True, "reason": "tile_paint", "counter": 3}) == [
        "SCENE DIRTY reason=tile_paint rev=3",
        "undo=0 redo=0",
    ]
