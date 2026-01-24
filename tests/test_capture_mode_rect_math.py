from __future__ import annotations


def test_normalize_rect_and_dimensions() -> None:
    from engine.capture_mode import Rect, normalize_rect

    r = normalize_rect(5, 7, 2, 3)
    assert isinstance(r, Rect)
    assert (r.x0, r.y0, r.x1, r.y1) == (2, 3, 5, 7)
    assert r.w == 4
    assert r.h == 5


def test_rect_w_h_inclusive() -> None:
    from engine.capture_mode import Rect

    r = Rect(x0=1, y0=1, x1=1, y1=1)
    assert r.w == 1
    assert r.h == 1

