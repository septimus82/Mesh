from __future__ import annotations

from engine.culling import rect_intersects


def test_culling_rect_intersects() -> None:
    assert rect_intersects((0.0, 0.0, 10.0, 10.0), (5.0, 5.0, 15.0, 15.0)) is True
    assert rect_intersects((0.0, 0.0, 10.0, 10.0), (10.0, 10.0, 20.0, 20.0)) is True
    assert rect_intersects((0.0, 0.0, 10.0, 10.0), (11.0, 0.0, 20.0, 10.0)) is False
