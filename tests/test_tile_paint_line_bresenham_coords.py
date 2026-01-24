from __future__ import annotations


def test_tile_paint_line_bresenham_coords() -> None:
    from engine.tile_paint_mode import line_coords_4_connected

    assert line_coords_4_connected(x0=0, y0=0, x1=2, y1=2) == [
        (0, 0),
        (1, 0),
        (1, 1),
        (2, 1),
        (2, 2),
    ]

