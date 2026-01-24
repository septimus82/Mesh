from __future__ import annotations


def test_tile_paint_rect_fill_coords() -> None:
    from engine.tile_paint_mode import rect_fill_coords

    assert rect_fill_coords(x0=1, y0=1, x1=3, y1=3) == {
        (1, 1),
        (2, 1),
        (3, 1),
        (1, 2),
        (2, 2),
        (3, 2),
        (1, 3),
        (2, 3),
        (3, 3),
    }

