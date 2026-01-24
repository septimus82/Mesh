from __future__ import annotations


def test_entity_select_overlay_shows_last_props_action_line() -> None:
    from engine.ui import format_entity_select_overlay_lines

    payload = {
        "enabled": True,
        "selected_ids": [],
        "dup_count": 0,
        "dup_primary": "",
        "transform_action": "",
        "transform_count": 0,
        "clipboard_count": 0,
        "clipboard_primary": "",
        "props_action": "set_tag",
        "props_changed": 2,
        "config_action": "tz_set_radius",
        "config_changed": 1,
    }
    lines = format_entity_select_overlay_lines(payload)
    assert "props=set_tag changed=2" in "\n".join(lines)
    assert "config=tz_set_radius changed=1" in "\n".join(lines)
