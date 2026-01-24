from __future__ import annotations


def test_command_palette_disabled_reason_stable() -> None:
    from engine.ui import format_command_palette_overlay_lines

    payload = {
        "enabled": True,
        "query": "",
        "dirty": True,
        "rev": 3,
        "armed": False,
        "undo": 0,
        "redo": 0,
        "active_mode": "tile_paint",
        "prompt_active": False,
        "rows": [
            {"kind": "section", "title": "Scene"},
            {"kind": "command", "id": "scene.persist", "title": "Persist Scene", "hotkey_hint": "Ctrl+S", "enabled": False, "disabled_reason": "not_armed"},
        ],
        "selected_row": 0,
    }
    lines = format_command_palette_overlay_lines(payload)
    assert "-- Scene --" in lines[1]
    assert "Persist Scene [disabled: not_armed]" in lines[2]

