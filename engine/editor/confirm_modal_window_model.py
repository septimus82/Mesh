"""
Pure model helpers for confirm modal scrolling/windowing.
"""

from typing import List, Tuple


def clamp_scroll(scroll_y: int, total_rows: int, visible_rows: int) -> int:
    """Clamp scroll position to valid range."""
    max_scroll = max(0, total_rows - visible_rows)
    return max(0, min(scroll_y, max_scroll))

def slice_lines(lines: List[str], scroll_y: int, visible_rows: int) -> Tuple[List[str], int]:
    """Slice lines for display based on scroll."""
    clamped = clamp_scroll(scroll_y, len(lines), visible_rows)
    end = min(len(lines), clamped + visible_rows)
    return lines[clamped:end], clamped
