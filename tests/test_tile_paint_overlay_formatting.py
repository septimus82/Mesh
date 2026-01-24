from __future__ import annotations


def test_tile_paint_overlay_formatting_lines() -> None:
    from engine.ui import format_tile_paint_overlay_lines

    payload = {
        "enabled": True,
        "layer_id": "Ground",
        "tile_id": 5,
        "tool": "brush",
        "slots": {1: 9, 3: 12},
        "recent": [5, 9, 12],
        "hover": {"tx": 3, "ty": 7, "world_x": 48.0, "world_y": 32.0},
    }
    assert format_tile_paint_overlay_lines(payload) == [
        "TILE PAINT: ON",
        "layer=Ground tile=5",
        "tool=brush hover=(3,7) world=(48.0,32.0)",
        "slots: 1=9 3=12",
        "recent: 5,9,12",
    ]
