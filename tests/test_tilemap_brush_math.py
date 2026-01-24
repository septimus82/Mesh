import pytest

from engine.tilemap_brush import apply_brush, validate_brush


def test_tilemap_brush_anchor_tl_and_mask_behavior():
    # 4x3 grid tiles indexed row-major
    tiles = [0] * 12
    brush = validate_brush(
        {
            "id": "b",
            "w": 3,
            "h": 3,
            "mask_tile": -1,
            "tiles": [
                [12, 13, 14],
                [15, -1, 16],
                [17, 18, 19],
            ],
        }
    )

    out = apply_brush(tiles, width=4, height=3, x=1, y=0, brush=brush, anchor="tl", clip=False)

    # Expected placements (origin at (1,0))
    # Row 0: (1,0)=12 (2,0)=13 (3,0)=14
    assert out[0:4] == [0, 12, 13, 14]
    # Row 1: (1,1)=15 (2,1)=masked (3,1)=16
    assert out[4:8] == [0, 15, 0, 16]
    # Row 2: (1,2)=17 (2,2)=18 (3,2)=19
    assert out[8:12] == [0, 17, 18, 19]


def test_tilemap_brush_anchor_center_places_middle_cell_at_xy():
    tiles = [0] * 25  # 5x5
    brush = validate_brush(
        {
            "id": "b",
            "w": 3,
            "h": 3,
            "tiles": [
                [1, 2, 3],
                [4, 5, 6],
                [7, 8, 9],
            ],
        }
    )

    out = apply_brush(tiles, width=5, height=5, x=2, y=2, brush=brush, anchor="center", clip=False)

    # Center anchor means brush(1,1)=5 lands at (2,2)
    center_idx = 2 * 5 + 2
    assert out[center_idx] == 5

    # Top-left of brush should be at (1,1)
    assert out[1 * 5 + 1] == 1
    assert out[1 * 5 + 2] == 2
    assert out[1 * 5 + 3] == 3


def test_tilemap_brush_out_of_bounds_errors_without_clip():
    tiles = [0] * 4  # 2x2
    brush = validate_brush({"id": "b", "w": 2, "h": 2, "tiles": [[1, 2], [3, 4]]})

    with pytest.raises(IndexError):
        apply_brush(tiles, width=2, height=2, x=1, y=1, brush=brush, anchor="tl", clip=False)


def test_tilemap_brush_out_of_bounds_clips_with_flag():
    tiles = [0] * 4  # 2x2
    brush = validate_brush({"id": "b", "w": 2, "h": 2, "tiles": [[1, 2], [3, 4]]})

    out = apply_brush(tiles, width=2, height=2, x=1, y=1, brush=brush, anchor="tl", clip=True)
    # Only (1,1) is in-bounds
    assert out == [0, 0, 0, 1]
