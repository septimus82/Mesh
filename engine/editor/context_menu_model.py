"""Context menu model for the editor.

This module provides pure dataclasses and functions for computing the
context menu layout and handling hit testing. No rendering or state
management - just deterministic geometry computation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Tuple

# Layout constants
CONTEXT_MENU_WIDTH = 180
CONTEXT_MENU_ITEM_HEIGHT = 24
CONTEXT_MENU_PADDING_X = 12
CONTEXT_MENU_PADDING_Y = 4
CONTEXT_MENU_FONT_SIZE = 12


@dataclass(frozen=True, slots=True)
class ContextMenuRect:
    """A simple rectangle for context menu hit testing."""

    x: float
    y: float
    w: float
    h: float

    def contains_point(self, px: float, py: float) -> bool:
        """Check if point is inside rectangle."""
        return self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h


@dataclass(frozen=True, slots=True)
class ContextMenuItem:
    """A single context menu item."""

    id: str
    label: str
    enabled: bool = True
    shortcut: str = ""
    separator: bool = False


@dataclass(frozen=True, slots=True)
class ContextMenuLayout:
    """Computed layout for the context menu."""

    rect: ContextMenuRect
    items_with_rects: Tuple[Tuple[ContextMenuItem, ContextMenuRect], ...]


def build_context_menu_items(controller: Any) -> List[ContextMenuItem]:
    """Build the context menu items based on current editor state.

    Args:
        controller: The editor controller.

    Returns:
        List of ContextMenuItem with items enabled/disabled appropriately.
    """
    has_selection = getattr(controller, "selected_entity", None) is not None

    items: List[ContextMenuItem] = [
        ContextMenuItem(
            id="ctx_edit",
            label="Edit",
            enabled=has_selection,
        ),
        ContextMenuItem(id="ctx_separator_edit", label="", enabled=False, separator=True),
        ContextMenuItem(
            id="ctx_duplicate",
            label="Duplicate",
            enabled=has_selection,
            shortcut="Ctrl+D",
        ),
        ContextMenuItem(
            id="ctx_delete",
            label="Delete",
            enabled=has_selection,
            shortcut="Del",
        ),
        ContextMenuItem(id="ctx_separator_mutate", label="", enabled=False, separator=True),
        ContextMenuItem(
            id="ctx_focus",
            label="Focus",
            enabled=has_selection,
            shortcut="F",
        ),
    ]

    return items


def compute_context_menu_layout(
    x: float,
    y: float,
    items: List[ContextMenuItem],
    window_w: int,
    window_h: int,
) -> ContextMenuLayout:
    """Compute the context menu layout at the given position.

    The menu is clamped to stay within window bounds.

    Args:
        x: Screen X coordinate where menu was opened.
        y: Screen Y coordinate where menu was opened.
        items: List of menu items.
        window_w: Window width in pixels.
        window_h: Window height in pixels.

    Returns:
        ContextMenuLayout with all rectangles computed.
    """
    # Calculate menu dimensions
    menu_height = len(items) * CONTEXT_MENU_ITEM_HEIGHT + CONTEXT_MENU_PADDING_Y * 2
    menu_width = CONTEXT_MENU_WIDTH

    # Clamp to window bounds
    # Menu opens below and to the right of cursor by default
    menu_x = x
    menu_y = y - menu_height  # Menu grows downward from cursor

    # Clamp X: if menu would go off right edge, flip to left of cursor
    if menu_x + menu_width > window_w:
        menu_x = max(0, window_w - menu_width)

    # Clamp X: ensure not off left edge
    if menu_x < 0:
        menu_x = 0

    # Clamp Y: if menu would go off bottom, flip to above cursor
    if menu_y < 0:
        menu_y = y  # Position above cursor instead

    # Clamp Y: if still off bottom (small window), clamp to 0
    if menu_y < 0:
        menu_y = 0

    # Clamp Y: ensure not off top edge
    if menu_y + menu_height > window_h:
        menu_y = max(0, window_h - menu_height)

    menu_rect = ContextMenuRect(
        x=menu_x,
        y=menu_y,
        w=menu_width,
        h=menu_height,
    )

    # Compute item rectangles (items stack from top to bottom)
    items_with_rects: List[Tuple[ContextMenuItem, ContextMenuRect]] = []
    current_y = menu_y + menu_height - CONTEXT_MENU_PADDING_Y - CONTEXT_MENU_ITEM_HEIGHT

    for item in items:
        item_rect = ContextMenuRect(
            x=menu_x,
            y=current_y,
            w=menu_width,
            h=CONTEXT_MENU_ITEM_HEIGHT,
        )
        items_with_rects.append((item, item_rect))
        current_y -= CONTEXT_MENU_ITEM_HEIGHT

    return ContextMenuLayout(
        rect=menu_rect,
        items_with_rects=tuple(items_with_rects),
    )


def hit_test_context_menu(x: float, y: float, layout: ContextMenuLayout) -> str | None:
    """Test if a point hits a context menu item.

    Args:
        x: Screen X coordinate.
        y: Screen Y coordinate.
        layout: The context menu layout.

    Returns:
        Item ID if hit, None otherwise.
    """
    for item, rect in layout.items_with_rects:
        if item.separator:
            continue
        if rect.contains_point(x, y):
            return item.id
    return None


def hit_test_context_menu_bounds(x: float, y: float, layout: ContextMenuLayout) -> bool:
    """Test if a point is within the context menu bounds.

    Args:
        x: Screen X coordinate.
        y: Screen Y coordinate.
        layout: The context menu layout.

    Returns:
        True if point is within menu bounds.
    """
    return layout.rect.contains_point(x, y)
