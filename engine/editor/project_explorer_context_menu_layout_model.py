"""Layout helpers for Project Explorer context menu."""
from __future__ import annotations


def clamp_menu_rect(
    anchor_x: int,
    anchor_y: int,
    menu_w: int,
    menu_h: int,
    viewport_w: int,
    viewport_h: int,
) -> tuple[int, int]:
    """Clamp menu position to keep it fully within the viewport."""
    x = int(anchor_x)
    y = int(anchor_y)
    if x + menu_w > viewport_w:
        x = max(0, viewport_w - menu_w)
    if y + menu_h > viewport_h:
        y = max(0, viewport_h - menu_h)
    return (int(x), int(y))
