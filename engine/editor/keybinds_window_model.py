"""
Pure logic model for the Keybinds modal UI windowing.

Handles view slicing, scroll clamping, and selection bounds.
"""
from __future__ import annotations

import math
from typing import Sequence, Tuple, TypeVar

T = TypeVar("T")

def clamp_scroll(
    scroll_y: float,
    total_rows: int,
    row_height: float,
    viewport_height: float
) -> float:
    """Clamp scroll position to valid range."""
    total_height = total_rows * row_height
    max_scroll = max(0.0, total_height - viewport_height)
    return max(0.0, min(scroll_y, max_scroll))

def auto_scroll_to_selection(
    scroll_y: float,
    selected_index: int,
    row_height: float,
    viewport_height: float,
    margin_rows: int = 1
) -> float:
    """Calculate new scroll position to ensure selection is visible."""
    if selected_index < 0:
        return scroll_y

    top_y = selected_index * row_height
    bottom_y = top_y + row_height

    # Add margins
    margin_px = margin_rows * row_height

    # Current viewport bounds
    curr_top = scroll_y
    curr_bottom = scroll_y + viewport_height

    # If above viewport
    if top_y < curr_top + margin_px:
        # Align top
        return max(0.0, top_y - margin_px)

    # If below viewport
    if bottom_y > curr_bottom - margin_px:
        # Align bottom
        return max(0.0, bottom_y - viewport_height + margin_px)

    return scroll_y

def slice_visible_rows(
    rows: Sequence[T],
    scroll_y: float,
    viewport_height: float,
    row_height: float,
    overscan: int = 2
) -> Tuple[int, int, list[T]]:
    """Return (start_idx, end_idx, visible_slice) for the current scroll data."""
    if not rows:
        return (0, 0, [])

    total_count = len(rows)
    # Calculate index range
    start_y = scroll_y
    # Ensure start_y is not negative
    start_y = max(0.0, start_y)

    start_index = int(math.floor(start_y / row_height))
    visible_count = int(math.ceil(viewport_height / row_height))

    # Apply overscan
    start_index = max(0, start_index - overscan)
    end_index = min(total_count, start_index + visible_count + 2 * overscan)

    return (start_index, end_index, list(rows[start_index:end_index]))
