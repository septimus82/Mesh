from __future__ import annotations


def test_extract_tiles_in_rect_row_major() -> None:
    from engine.capture_mode import extract_tiles_in_rect, normalize_rect

    # map 4x3, tiles are row-major with y=0 as top row.
    # row0: 1 2 3 4
    # row1: 5 6 7 8
    # row2: 9 0 0 0
    scene = {
        "tilemap": {
            "tile_layers": [
                {"id": "Ground", "z": -100, "tiles": [1, 2, 3, 4, 5, 6, 7, 8, 9, 0, 0, 0]},
            ]
        }
    }

    rect = normalize_rect(1, 0, 2, 1)  # x=1..2, y=0..1
    out = extract_tiles_in_rect(scene, layer_id="Ground", rect=rect, map_width=4, map_height=3)
    assert out == [2, 3, 6, 7]

