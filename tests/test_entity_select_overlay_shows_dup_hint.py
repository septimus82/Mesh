from __future__ import annotations


def test_entity_select_overlay_shows_dup_hint() -> None:
    from engine.ui import format_entity_select_overlay_lines

    lines = format_entity_select_overlay_lines(
        {
            "enabled": True,
            "selected_ids": ["b__dup1", "a__dup1"],
            "primary_id": "b__dup1",
            "primary": {"id": "b__dup1", "prefab_id": "slime_blob", "pos": {"x": 0.0, "y": 0.0}},
            "dup_count": 2,
            "dup_primary": "b__dup1",
        }
    )
    assert "dup=2 primary=b__dup1" in lines

