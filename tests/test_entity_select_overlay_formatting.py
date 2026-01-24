from __future__ import annotations


def test_entity_select_overlay_formatting() -> None:
    from engine.ui import format_entity_select_overlay_lines

    assert format_entity_select_overlay_lines({"enabled": False}) == []
    assert format_entity_select_overlay_lines({"enabled": True, "selected_ids": []}) == ["SELECT none"]
    assert format_entity_select_overlay_lines(
        {"enabled": True, "selected_ids": ["e1"], "primary_id": "e1", "primary": {"id": "e1", "prefab_id": "slime_blob", "pos": {"x": 1.25, "y": 2.5}}}
    ) == ["SELECT 1 id=e1 prefab=slime_blob pos=(1.2,2.5)"]
    assert format_entity_select_overlay_lines({"enabled": True, "selected_ids": ["b", "a", "c"], "primary_id": "b"}) == [
        "SELECT 3 primary=b (first 5: a,b,c)"
    ]
