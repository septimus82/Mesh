from __future__ import annotations

from typing import Any, Iterable, Sequence
import engine.optional_arcade as optional_arcade
from .occluders import Rect

Point = tuple[float, float]
Polygon = Sequence[Point]


def _try_call(fn: Any, *args: object, **kwargs: object) -> None:
    if fn is None:
        return
    try:
        fn(*args, **kwargs)
    except Exception:  # noqa: BLE001  # REASON: optional debug draw callbacks should fail closed without breaking lighting debug rendering
        return


def draw_occluder_rects(window: Any, rects: Sequence[Rect]) -> None:  # noqa: ARG001
    if optional_arcade.arcade is None:  # pragma: no cover
        return
    draw_outline = getattr(optional_arcade.arcade, "draw_rectangle_outline", None)
    for r in rects:
        cx = float(r.x + r.width / 2.0)
        cy = float(r.y + r.height / 2.0)
        _try_call(draw_outline, cx, cy, float(r.width), float(r.height), (255, 0, 0), 2)


def draw_shadow_polygons(window: Any, polys: Iterable[Polygon]) -> None:  # noqa: ARG001
    if optional_arcade.arcade is None:  # pragma: no cover
        return
    draw_poly = getattr(optional_arcade.arcade, "draw_polygon_outline", None)
    draw_line_strip = getattr(optional_arcade.arcade, "draw_line_strip", None)
    for poly in polys:
        points = [(float(x), float(y)) for x, y in poly]
        if len(points) < 2:
            continue
        if callable(draw_poly):
            _try_call(draw_poly, points, (255, 255, 0), 2)
        else:
            closed = points + [points[0]]
            _try_call(draw_line_strip, closed, (255, 255, 0), 2)
