from __future__ import annotations

from engine.lighting.occluders import Rect, build_occluders_from_tile_layer


def test_occluder_merge_rects_deterministic() -> None:
    grid = [
        [0, 1, 1, 0, 0, 0],
        [0, 1, 1, 0, 1, 1],
        [0, 0, 0, 0, 1, 1],
        [0, 0, 0, 0, 0, 0],
    ]
    rects = build_occluders_from_tile_layer(grid, (32, 32))
    rects2 = build_occluders_from_tile_layer(grid, (32, 32))
    assert rects == rects2

    assert rects == [
        Rect(x=128.0, y=32.0, width=64.0, height=64.0),
        Rect(x=32.0, y=64.0, width=64.0, height=64.0),
    ]

