from __future__ import annotations


def test_entity_paint_overlay_formatting_lines() -> None:
    from engine.ui import format_entity_paint_overlay_lines

    payload = {
        "enabled": True,
        "prefab_id": "slime_blob",
        "prefab_index": 2,
        "prefab_count": 5,
        "filter_mode": "enemy",
        "persist_armed": True,
        "slots": {1: "slime_blob", 2: "crate"},
        "recent": ["slime_blob", "crate"],
        "hover": {"world_x": 10.0, "world_y": 20.0, "tx": 1, "ty": 2},
        "hover_entity": {"id": "e1", "prefab_id": "slime_blob", "name": "Blob"},
    }
    assert format_entity_paint_overlay_lines(payload) == [
        "ENTITY PAINT: ON",
        "prefab=slime_blob (index 2/5) [filter=enemy]",
        "hover_world=(10.0,20.0) hover_tile=(1,2)",
        "hover_entity=e1/slime_blob/Blob",
        "persist=ARMED",
        "slots: 1=slime_blob 2=crate",
        "recent: slime_blob,crate",
    ]
