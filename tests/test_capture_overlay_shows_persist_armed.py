from __future__ import annotations


def test_capture_overlay_shows_persist_armed() -> None:
    from engine.ui import format_capture_overlay_lines

    payload = {
        "enabled": True,
        "mode": "brush",
        "rect": {"x0": 0, "y0": 0, "x1": 0, "y1": 0, "w": 1, "h": 1},
        "layers": 1,
        "include_entities": False,
        "persist_armed": True,
        "hover": {"tx": 0, "ty": 0, "tile_id": 1, "layer_id": "Ground"},
    }
    lines = format_capture_overlay_lines(payload)
    assert any("Persist=ON" in line for line in lines)

