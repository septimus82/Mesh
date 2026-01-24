from __future__ import annotations


def test_capture_mode_builds_stamp_and_brush_shapes() -> None:
    from engine.capture_mode import build_brush_payload, build_stamp_payload, normalize_rect

    scene = {
        "tilemap": {"tile_layers": [{"id": "Ground", "z": -100, "tiles": [1, 2, 3, 4]}]},
        "entities": [{"id": "e1", "prefab_id": "crate", "x": 8.0, "y": 8.0}],
    }
    rect = normalize_rect(0, 0, 1, 1)

    stamp = build_stamp_payload(
        scene,
        rect=rect,
        map_width=2,
        map_height=2,
        tile_width=16,
        tile_height=16,
        include_entities=True,
    )
    assert set(stamp.keys()) >= {"id", "width", "height", "tiles", "entities"}
    assert stamp["width"] == 2
    assert stamp["height"] == 2

    brush = build_brush_payload(
        scene,
        rect=rect,
        map_width=2,
        map_height=2,
        layer_id="Ground",
        filter_mode="all",
        filter_value=0,
    )
    assert set(brush.keys()) == {"id", "w", "h", "mask_tile", "tiles"}
    assert brush["w"] == 2
    assert brush["h"] == 2

