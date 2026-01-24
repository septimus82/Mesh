from __future__ import annotations


def test_capture_overlay_formatting_lines() -> None:
    from engine.ui import format_capture_overlay_lines

    payload = {
        "enabled": True,
        "mode": "stamp",
        "rect": {"x0": 1, "y0": 2, "x1": 3, "y1": 4, "w": 3, "h": 3},
        "layers": 2,
        "include_entities": True,
        "persist_armed": True,
        "persist_status": "CAPTURE_PERSIST ok path=... wrote=Y",
        "hover": {"tx": 2, "ty": 3, "tile_id": 7, "layer_id": "Ground"},
    }
    assert format_capture_overlay_lines(payload) == [
        "CAPTURE: ON STAMP",
        "rect=(1,2)-(3,4) w=3 h=3",
        "layers=2 include_entities=Y",
        "Persist=ON CAPTURE_PERSIST ok path=... wrote=Y",
        "hover=(2,3) tile=7 layer=Ground",
        "hint: Drag=select Tab=type Shift=entities Enter=copy Esc=close",
    ]
