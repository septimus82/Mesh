from __future__ import annotations


def test_entity_select_overlay_multiselect_formatting() -> None:
    from engine.ui import format_entity_select_overlay_lines

    assert format_entity_select_overlay_lines({"enabled": True, "selected_ids": []}) == ["SELECT none"]
    assert format_entity_select_overlay_lines(
        {
            "enabled": True,
            "selected_ids": ["z", "y", "x", "w", "v", "u"],
            "primary_id": "y",
        }
    ) == ["SELECT 6 primary=y (first 5: u,v,w,x,y)"]
