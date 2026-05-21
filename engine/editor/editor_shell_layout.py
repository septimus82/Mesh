"""Editor shell layout computation.

This module provides pure dataclasses and functions for computing the
editor shell layout based on window dimensions. No rendering or state
management - just deterministic geometry computation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


# Layout constants
TOP_BAR_HEIGHT = 48
BOTTOM_BAR_HEIGHT = 28  # matches existing status bar
DOCK_WIDTH = 320  # Default dock width
MIN_VIEWPORT_SIZE = 100

# Dock resize constants
DOCK_MIN_W = 220
DOCK_MAX_W = 520
VIEWPORT_MIN_W = 320
SPLITTER_W = 6


@dataclass(frozen=True, slots=True)
class DockSizing:
    """Dock sizing configuration."""
    left_w: int = DOCK_WIDTH
    right_w: int = DOCK_WIDTH


@dataclass(frozen=True, slots=True)
class Rect:
    """A simple rectangle defined by left, right, bottom, top."""
    left: float
    right: float
    bottom: float
    top: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.top - self.bottom

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2.0

    @property
    def center_y(self) -> float:
        return (self.bottom + self.top) / 2.0

    def contains_point(self, x: float, y: float) -> bool:
        return self.left <= x <= self.right and self.bottom <= y <= self.top


@dataclass(frozen=True, slots=True)
class EditorShellLayout:
    """Complete editor shell layout with all panel rectangles."""
    top_bar: Rect
    left_dock: Rect
    right_dock: Rect
    viewport: Rect
    bottom_bar: Rect
    left_splitter: Rect
    right_splitter: Rect
    window_width: int
    window_height: int


@dataclass(slots=True)
class DockTabState:
    """Tracks which tabs are active in each dock."""
    left_tab: str = "Scene"      # "Project", "Scene", or "Outliner"
    right_tab: str = "Inspector"  # "Inspector", "Assets", "Items", "History", "Problems", or "Debug"


def clamp_dock_width(width: int, window_width: int, other_dock_width: int) -> int:
    """Clamp dock width to valid bounds.

    Args:
        width: Desired dock width.
        window_width: Total window width.
        other_dock_width: Width of the other dock.

    Returns:
        Clamped dock width.
    """
    # Ensure minimum viewport width
    max_available = window_width - other_dock_width - VIEWPORT_MIN_W - SPLITTER_W * 2
    max_w = min(DOCK_MAX_W, max(DOCK_MIN_W, max_available))
    return max(DOCK_MIN_W, min(width, max_w))


def compute_editor_shell_layout(
    window_width: int,
    window_height: int,
    left_dock_w: int | None = None,
    right_dock_w: int | None = None,
) -> EditorShellLayout:
    """Compute the editor shell layout from window dimensions.

    Args:
        window_width: Window width in pixels.
        window_height: Window height in pixels.
        left_dock_w: Optional custom left dock width.
        right_dock_w: Optional custom right dock width.

    Returns:
        EditorShellLayout with all panel rectangles computed.
    """
    w = float(max(1, window_width))
    h = float(max(1, window_height))

    # Use provided widths or defaults
    left_w = left_dock_w if left_dock_w is not None else DOCK_WIDTH
    right_w = right_dock_w if right_dock_w is not None else DOCK_WIDTH

    # Clamp dock widths to valid bounds
    # First clamp left with default right
    left_w = clamp_dock_width(left_w, int(w), right_w)
    # Then clamp right with actual left
    right_w = clamp_dock_width(right_w, int(w), left_w)
    # Re-clamp left in case right changed significantly
    left_w = clamp_dock_width(left_w, int(w), right_w)

    # Top bar: full width, at top
    top_bar = Rect(
        left=0.0,
        right=w,
        bottom=h - TOP_BAR_HEIGHT,
        top=h,
    )

    # Bottom bar: full width, at bottom
    bottom_bar = Rect(
        left=0.0,
        right=w,
        bottom=0.0,
        top=BOTTOM_BAR_HEIGHT,
    )

    # Content area between top and bottom bars
    content_bottom = bottom_bar.top
    content_top = top_bar.bottom

    # Left dock: from left edge, full content height
    left_dock = Rect(
        left=0.0,
        right=float(left_w),
        bottom=content_bottom,
        top=content_top,
    )

    # Left splitter: between left dock and viewport
    left_splitter = Rect(
        left=left_dock.right,
        right=left_dock.right + SPLITTER_W,
        bottom=content_bottom,
        top=content_top,
    )

    # Right dock: from right edge, full content height
    right_dock = Rect(
        left=w - float(right_w),
        right=w,
        bottom=content_bottom,
        top=content_top,
    )

    # Right splitter: between viewport and right dock
    right_splitter = Rect(
        left=right_dock.left - SPLITTER_W,
        right=right_dock.left,
        bottom=content_bottom,
        top=content_top,
    )

    # Viewport: center area between splitters
    viewport = Rect(
        left=left_splitter.right,
        right=right_splitter.left,
        bottom=content_bottom,
        top=content_top,
    )

    return EditorShellLayout(
        top_bar=top_bar,
        left_dock=left_dock,
        right_dock=right_dock,
        viewport=viewport,
        bottom_bar=bottom_bar,
        left_splitter=left_splitter,
        right_splitter=right_splitter,
        window_width=window_width,
        window_height=window_height,
    )


def clamp_rects_to_window(
    layout: EditorShellLayout,
    window_width: int,
    window_height: int,
) -> EditorShellLayout:
    """Clamp all layout rectangles to fit within window bounds.

    Args:
        layout: The layout to clamp.
        window_width: Window width in pixels.
        window_height: Window height in pixels.

    Returns:
        New EditorShellLayout with all rectangles clamped.
    """
    def clamp_rect(r: Rect) -> Rect:
        return Rect(
            left=max(0.0, min(r.left, float(window_width))),
            right=max(0.0, min(r.right, float(window_width))),
            bottom=max(0.0, min(r.bottom, float(window_height))),
            top=max(0.0, min(r.top, float(window_height))),
        )

    return EditorShellLayout(
        top_bar=clamp_rect(layout.top_bar),
        left_dock=clamp_rect(layout.left_dock),
        right_dock=clamp_rect(layout.right_dock),
        viewport=clamp_rect(layout.viewport),
        bottom_bar=clamp_rect(layout.bottom_bar),
        left_splitter=clamp_rect(layout.left_splitter),
        right_splitter=clamp_rect(layout.right_splitter),
        window_width=window_width,
        window_height=window_height,
    )


def get_dock_tab_options() -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """Get the available tab options for each dock.

    Returns:
        Tuple of (left_tabs, right_tabs) where each is a tuple of tab names.
    """
    left_tabs = ("Project", "Scene", "Outliner")
    right_tabs = ("Inspector", "Assets", "Items", "History", "Problems", "Debug")
    return left_tabs, right_tabs


# Tab header constants
TAB_HEADER_HEIGHT = 32.0
TAB_PADDING = 2.0


@dataclass(frozen=True, slots=True)
class DockTabRects:
    """Hit regions for dock tabs."""
    left_tab_rects: dict[str, Rect]
    right_tab_rects: dict[str, Rect]


def compute_dock_tab_rects(layout: EditorShellLayout) -> DockTabRects:
    """Compute hit regions for all dock tabs.

    Args:
        layout: The computed editor shell layout.

    Returns:
        DockTabRects with hit regions for left and right dock tabs.
    """
    left_tabs, right_tabs = get_dock_tab_options()

    # Left dock tabs
    left_dock = layout.left_dock
    tab_y_bottom = left_dock.top - TAB_HEADER_HEIGHT
    tab_width = left_dock.width / len(left_tabs)

    left_rects: dict[str, Rect] = {}
    for i, tab_name in enumerate(left_tabs):
        tab_left = left_dock.left + i * tab_width
        tab_right = tab_left + tab_width
        left_rects[tab_name] = Rect(
            left=tab_left + TAB_PADDING,
            right=tab_right - TAB_PADDING,
            bottom=tab_y_bottom + TAB_PADDING,
            top=left_dock.top - TAB_PADDING,
        )

    # Right dock tabs
    right_dock = layout.right_dock
    tab_width = right_dock.width / len(right_tabs)

    right_rects: dict[str, Rect] = {}
    for i, tab_name in enumerate(right_tabs):
        tab_left = right_dock.left + i * tab_width
        tab_right = tab_left + tab_width
        right_rects[tab_name] = Rect(
            left=tab_left + TAB_PADDING,
            right=tab_right - TAB_PADDING,
            bottom=tab_y_bottom + TAB_PADDING,
            top=right_dock.top - TAB_PADDING,
        )

    return DockTabRects(
        left_tab_rects=left_rects,
        right_tab_rects=right_rects,
    )


def hit_test_dock_tab(
    x: float,
    y: float,
    layout: EditorShellLayout,
) -> Tuple[str, str] | None:
    """Hit test for dock tab clicks.

    Args:
        x: Screen x coordinate.
        y: Screen y coordinate.
        layout: The computed editor shell layout.

    Returns:
        Tuple of ("left" or "right", tab_name) if a tab was hit, None otherwise.
    """
    tab_rects = compute_dock_tab_rects(layout)

    # Check left dock tabs
    for tab_name, rect in tab_rects.left_tab_rects.items():
        if rect.contains_point(x, y):
            return ("left", tab_name)

    # Check right dock tabs
    for tab_name, rect in tab_rects.right_tab_rects.items():
        if rect.contains_point(x, y):
            return ("right", tab_name)

    return None


def hit_test_splitter(
    x: float,
    y: float,
    layout: EditorShellLayout,
) -> str | None:
    """Hit test for splitter drags.

    Args:
        x: Screen x coordinate.
        y: Screen y coordinate.
        layout: The computed editor shell layout.

    Returns:
        "left" or "right" if a splitter was hit, None otherwise.
    """
    if layout.left_splitter.contains_point(x, y):
        return "left"
    if layout.right_splitter.contains_point(x, y):
        return "right"
    return None


# =============================================================================
# Dock Collapse / Maximize Viewport
# =============================================================================

def resolve_effective_dock_widths(
    left_collapsed: bool,
    right_collapsed: bool,
    viewport_maximized: bool,
    left_w: int,
    right_w: int,
    window_width: int,
) -> Tuple[int, int]:
    """Resolve effective dock widths based on collapse/maximize state.

    Args:
        left_collapsed: Whether the left dock is collapsed.
        right_collapsed: Whether the right dock is collapsed.
        viewport_maximized: Whether the viewport is maximized (hides both docks).
        left_w: The stored left dock width.
        right_w: The stored right dock width.
        window_width: Window width for clamping.

    Returns:
        Tuple of (left_w_effective, right_w_effective).
    """
    if viewport_maximized:
        return (0, 0)

    left_eff = 0 if left_collapsed else clamp_dock_width(left_w, window_width, right_w)
    right_eff = 0 if right_collapsed else clamp_dock_width(right_w, window_width, left_eff)

    return (left_eff, right_eff)


# =============================================================================
# Top Bar Controls (Dock Toggle + Maximize)
# =============================================================================

# Button dimensions
TOP_BAR_BUTTON_W = 28.0
TOP_BAR_BUTTON_H = 22.0
TOP_BAR_BUTTON_MARGIN = 4.0
TOP_BAR_BUTTON_RIGHT_OFFSET = 140.0  # Distance from right edge (before tool indicator)


@dataclass(frozen=True, slots=True)
class TopBarControls:
    """Hit regions for top bar dock/maximize controls."""
    toggle_left: Rect
    toggle_right: Rect
    toggle_max: Rect


def compute_top_bar_controls(layout: EditorShellLayout) -> TopBarControls:
    """Compute hit regions for top bar dock toggle controls.

    Controls are arranged right-to-left before the tool mode indicator:
    [L] [R] [M]

    Args:
        layout: The computed editor shell layout.

    Returns:
        TopBarControls with hit regions for each button.
    """
    bar = layout.top_bar
    btn_y_center = bar.center_y
    btn_bottom = btn_y_center - TOP_BAR_BUTTON_H / 2
    btn_top = btn_y_center + TOP_BAR_BUTTON_H / 2

    # Start from right offset, place buttons left-to-right: [L] [R] [M]
    start_x = bar.right - TOP_BAR_BUTTON_RIGHT_OFFSET

    # [L] toggle left dock
    toggle_left = Rect(
        left=start_x,
        right=start_x + TOP_BAR_BUTTON_W,
        bottom=btn_bottom,
        top=btn_top,
    )

    # [R] toggle right dock
    r_left = start_x + TOP_BAR_BUTTON_W + TOP_BAR_BUTTON_MARGIN
    toggle_right = Rect(
        left=r_left,
        right=r_left + TOP_BAR_BUTTON_W,
        bottom=btn_bottom,
        top=btn_top,
    )

    # [M] toggle maximize
    m_left = r_left + TOP_BAR_BUTTON_W + TOP_BAR_BUTTON_MARGIN
    toggle_max = Rect(
        left=m_left,
        right=m_left + TOP_BAR_BUTTON_W,
        bottom=btn_bottom,
        top=btn_top,
    )

    return TopBarControls(
        toggle_left=toggle_left,
        toggle_right=toggle_right,
        toggle_max=toggle_max,
    )


def hit_test_top_bar_controls(
    x: float,
    y: float,
    controls: TopBarControls,
) -> str | None:
    """Hit test for top bar control buttons.

    Args:
        x: Screen x coordinate.
        y: Screen y coordinate.
        controls: The computed top bar control regions.

    Returns:
        "toggle_left", "toggle_right", or "toggle_max" if hit, None otherwise.
    """
    if controls.toggle_left.contains_point(x, y):
        return "toggle_left"
    if controls.toggle_right.contains_point(x, y):
        return "toggle_right"
    if controls.toggle_max.contains_point(x, y):
        return "toggle_max"
    return None
