from __future__ import annotations

Rect = tuple[float, float, float, float]


def expand_rect(rect: Rect, margin: float) -> Rect:
    delta = float(margin)
    return (
        float(rect[0]) - delta,
        float(rect[1]) - delta,
        float(rect[2]) + delta,
        float(rect[3]) + delta,
    )


def rect_intersects(a: Rect, b: Rect) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def aabb_from_center(x: float, y: float, half_w: float, half_h: float) -> Rect:
    return (float(x) - float(half_w), float(y) - float(half_h), float(x) + float(half_w), float(y) + float(half_h))


def sprite_bounds(
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    scale: float = 1.0,
) -> Rect:
    half_w = float(width) * float(scale) * 0.5
    half_h = float(height) * float(scale) * 0.5
    return aabb_from_center(x, y, half_w, half_h)


def is_sprite_visible(camera_rect: Rect, sprite_rect: Rect, *, margin: float = 0.0) -> bool:
    return rect_intersects(expand_rect(camera_rect, margin), sprite_rect)
