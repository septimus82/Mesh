from __future__ import annotations


def test_command_palette_sections_render_stable() -> None:
    from engine.ui import format_command_palette_overlay_lines

    payload = {
        "enabled": True,
        "query": "sc",
        "dirty": False,
        "rev": 2,
        "armed": False,
        "undo": 1,
        "redo": 0,
        "active_mode": "none",
        "prompt_active": False,
        "rows": [
            {"kind": "section", "title": "Modes"},
            {"kind": "command", "id": "m1", "title": "Toggle Tile Paint", "hotkey_hint": "F11", "enabled": True, "disabled_reason": ""},
            {"kind": "section", "title": "Scene"},
            {"kind": "command", "id": "s1", "title": "Reload Scene", "hotkey_hint": "Ctrl+R", "enabled": True, "disabled_reason": ""},
        ],
        "selected_row": 1,
    }
    lines = format_command_palette_overlay_lines(payload)
    assert lines[0].startswith("COMMAND PALETTE: sc ")
    assert lines[1] == "-- Modes --"
    assert "Toggle Tile Paint" in lines[2] and "F11" in lines[2]
    assert lines[3] == "-- Scene --"
    assert "Reload Scene" in lines[4] and "Ctrl+R" in lines[4]

