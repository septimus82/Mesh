from __future__ import annotations


def test_extract_entities_in_rect_includes_and_sorts() -> None:
    from engine.capture_mode import extract_entities_in_rect, normalize_rect

    # map 4x3 tiles, 16px each. Rect covers tile coords x=1..2, y=0..1.
    rect = normalize_rect(1, 0, 2, 1)

    entities = [
        {"id": "z", "prefab_id": "crate", "x": 24.0, "y": 40.0},  # tile (1,0) => inside
        {"id": "a", "prefab_id": "crate", "x": 40.0, "y": 24.0},  # tile (2,1) => inside
        {"id": "b", "prefab_id": "barrel", "x": 8.0, "y": 40.0},  # tile (0,0) => outside
    ]

    out = extract_entities_in_rect(
        entities,
        rect=rect,
        map_width=4,
        map_height=3,
        tile_width=16,
        tile_height=16,
    )

    # Sorted by (prefab_id, id, x, y)
    assert out == [
        {"prefab_id": "crate", "x": 1, "y": 1, "id_suffix": "a"},
        {"prefab_id": "crate", "x": 0, "y": 0, "id_suffix": "z"},
    ]

