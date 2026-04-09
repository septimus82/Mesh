"""Editor overlay for hover highlights.

Renders hover highlights for UI chrome elements (menu bar, context menu, 
dock tabs, splitters) and optionally hovered entities in viewport.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Tuple

import engine.optional_arcade as optional_arcade
from engine.editor_hover_highlight_model import (
    HoverHighlightKind,
    HoverHighlightSpec,
    HighlightRect,
    is_ui_blocked,
    resolve_hover_highlights,
)
from engine.editor.editor_hover_dock_tab_query import (
    get_hovered_dock_tab,
    get_hovered_dock_tab_rect,
)
from engine.editor.editor_hover_query import (
    get_hovered_entity_id,
    get_hovered_entity_rect,
    get_hovered_inspector_field_key,
    get_hovered_inspector_field_rect,
    get_hovered_splitter,
    get_hovered_splitter_rect,
)
from engine.editor.editor_menu_hover_query import (
    get_context_menu_hover_id,
    get_context_menu_hover_rect,
    get_menu_hover_item_id,
    get_menu_hover_item_rect,
    get_menu_hover_title,
    get_menu_hover_title_rect,
)
from engine.editor.editor_modal_state_query import get_active_menu_id
from engine.logging_tools import get_logger
from engine.ui_overlays.common import UIElement

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController

logger = get_logger(__name__)

# Hover highlight colors (RGBA)
HOVER_HIGHLIGHT_FILL = (100, 180, 255, 30)  # Subtle blue fill
HOVER_HIGHLIGHT_BORDER = (100, 180, 255, 120)  # Matching border
HOVER_ENTITY_COLOR = (255, 200, 100, 150)  # Warm orange for entities
HOVER_SPLITTER_COLOR = (200, 200, 255, 100)  # Soft purple for splitters
HOVER_TOPBAR_BORDER = (140, 210, 255, 160)  # Bright border for top bar controls

# Line widths
HOVER_BORDER_WIDTH = 1.0
HOVER_ENTITY_BORDER_WIDTH = 1.5


def _get_color_for_kind(kind: HoverHighlightKind) -> Tuple[Tuple[int, ...], Tuple[int, ...]]:
    """Get fill and border colors for a highlight kind.
    
    Args:
        kind: The highlight kind.
        
    Returns:
        Tuple of (fill_color, border_color).
    """
    if kind == HoverHighlightKind.ENTITY_HOVER:
        # Entity hover: no fill, just border
        return (0, 0, 0, 0), HOVER_ENTITY_COLOR
    elif kind == HoverHighlightKind.TOPBAR_CONTROL:
        # Top bar controls: subtle border emphasis
        return (0, 0, 0, 0), HOVER_TOPBAR_BORDER
    elif kind == HoverHighlightKind.SPLITTER:
        # Splitter: subtle highlight
        return (200, 200, 255, 40), HOVER_SPLITTER_COLOR
    else:
        # UI elements: subtle fill + border
        return HOVER_HIGHLIGHT_FILL, HOVER_HIGHLIGHT_BORDER


def _get_line_width_for_kind(kind: HoverHighlightKind) -> float:
    """Get border line width for a highlight kind.
    
    Args:
        kind: The highlight kind.
        
    Returns:
        Line width in pixels.
    """
    if kind == HoverHighlightKind.ENTITY_HOVER:
        return HOVER_ENTITY_BORDER_WIDTH
    return HOVER_BORDER_WIDTH


class EditorHoverHighlightOverlay(UIElement):
    """Overlay for rendering hover highlights.
    
    Handles both UI-space highlights (menu bar, dock tabs, etc.) and
    world-space highlights (hovered entities in viewport).
    """

    def __init__(self, window: Any) -> None:
        """Initialize overlay.
        
        Args:
            window: Game window to query controller from.
        """
        super().__init__(window)
        self._visible = True
        self._cached_specs: Tuple[HoverHighlightSpec, ...] = ()

    @property
    def controller(self) -> "EditorModeController | None":
        """Get editor controller from window."""
        return getattr(self.window, "editor_controller", None)

    def update(self, dt: float) -> None:  # noqa: ARG002
        """Update overlay by computing current highlight specs."""
        controller = self.controller
        if controller is None or not getattr(controller, "active", False):
            self._cached_specs = ()
            return

        if not self._visible:
            self._cached_specs = ()
            return

        # Get window dimensions
        window_w = getattr(self.window, "width", 1280)
        window_h = getattr(self.window, "height", 720)

        # Check if UI is blocked
        block_ui = is_ui_blocked(controller)

        # Gather hover state from controller
        specs = resolve_hover_highlights(
            window_w=window_w,
            window_h=window_h,
            # Menu bar state
            hovered_menu_title=self._get_hovered_menu_title(controller),
            hovered_menu_title_rect=self._get_hovered_menu_title_rect(controller),
            hovered_menu_item_id=self._get_hovered_menu_item_id(controller),
            hovered_menu_item_rect=self._get_hovered_menu_item_rect(controller),
            hovered_top_bar_control_id=self._get_hovered_top_bar_control_id(controller),
            # Context menu state
            hovered_context_item_id=self._get_hovered_context_item_id(controller),
            hovered_context_item_rect=self._get_hovered_context_item_rect(controller),
            # Dock tab state
            hovered_dock_tab=self._get_hovered_dock_tab(controller),
            hovered_dock_tab_rect=self._get_hovered_dock_tab_rect(controller),
            # Splitter state
            hovered_splitter=self._get_hovered_splitter(controller),
            hovered_splitter_rect=self._get_hovered_splitter_rect(controller),
            # Inspector field state
            hovered_inspector_field_key=self._get_hovered_inspector_field_key(controller),
            hovered_inspector_field_rect=self._get_hovered_inspector_field_rect(controller),
            # Entity hover state
            hovered_entity_id=self._get_hovered_entity_id(controller),
            hovered_entity_rect=self._get_hovered_entity_rect(controller),
            # Block flag
            block_ui=block_ui,
        )

        self._cached_specs = specs

    def draw(self) -> None:
        """Draw UI-space hover highlights."""
        controller = self.controller
        if controller is None or not getattr(controller, "active", False):
            return

        if not self._visible:
            return

        arcade = optional_arcade.arcade
        if arcade is None:
            return

        # Draw only UI-space highlights
        for spec in self._cached_specs:
            if not spec.is_world_space:
                self._draw_highlight(arcade, spec)

    def draw_world(self) -> None:
        """Draw world-space hover highlights.
        
        Should be called within the world camera context.
        """
        controller = self.controller
        if controller is None or not getattr(controller, "active", False):
            return

        if not self._visible:
            return

        arcade = optional_arcade.arcade
        if arcade is None:
            return

        # Draw only world-space highlights
        for spec in self._cached_specs:
            if spec.is_world_space:
                self._draw_highlight(arcade, spec)

    def draw_ui(self) -> None:
        """Draw UI elements (no-op for this overlay)."""
        pass

    def _draw_highlight(self, arcade: Any, spec: HoverHighlightSpec) -> None:
        """Draw a single hover highlight.
        
        Args:
            arcade: Arcade module reference.
            spec: Hover highlight specification.
        """
        rect = spec.rect
        fill_color, border_color = _get_color_for_kind(spec.kind)
        line_width = _get_line_width_for_kind(spec.kind)

        # Draw fill if color has alpha
        if fill_color[3] > 0:
            # Use draw_lrbt_rectangle_filled (left, right, bottom, top, color)
            draw_lrbt = getattr(arcade, "draw_lrbt_rectangle_filled", None)
            if draw_lrbt is not None:
                try:
                    draw_lrbt(rect.left, rect.right, rect.bottom, rect.top, fill_color)
                except (AttributeError, TypeError):
                    pass

        # Draw border
        self._draw_rect_border(arcade, rect, border_color, line_width)

    def _draw_rect_border(
        self,
        arcade: Any,
        rect: HighlightRect,
        color: Tuple[int, ...],
        line_width: float,
    ) -> None:
        """Draw rectangle border using line segments.
        
        Args:
            arcade: Arcade module reference.
            rect: Rectangle to draw border around.
            color: Line color (RGBA tuple).
            line_width: Line thickness in pixels.
        """
        draw_line = getattr(arcade, "draw_line", None)
        if draw_line is None:
            return

        try:
            # Bottom edge
            draw_line(rect.left, rect.bottom, rect.right, rect.bottom, color, line_width)
            # Right edge
            draw_line(rect.right, rect.bottom, rect.right, rect.top, color, line_width)
            # Top edge
            draw_line(rect.right, rect.top, rect.left, rect.top, color, line_width)
            # Left edge
            draw_line(rect.left, rect.top, rect.left, rect.bottom, color, line_width)
        except (AttributeError, TypeError):
            pass

    # --- State accessors ---

    def _get_hovered_menu_title(self, controller: Any) -> str | None:
        """Get hovered menu title from controller."""
        # Menu bar highlighting uses _menu_hover_item_id for both title and items
        # The title is hovered when menu is not active but hovering on title
        active_menu = get_active_menu_id(controller)
        if not active_menu:
            # Check if hovering menu title (not item)
            return get_menu_hover_title(controller)
        return None

    def _get_hovered_menu_title_rect(self, controller: Any) -> Tuple[float, float, float, float] | None:
        """Get hovered menu title rect from controller."""
        return get_menu_hover_title_rect(controller)

    def _get_hovered_menu_item_id(self, controller: Any) -> str | None:
        """Get hovered menu item ID from controller."""
        active_menu = get_active_menu_id(controller)
        if active_menu:
            return get_menu_hover_item_id(controller)
        return None

    def _get_hovered_menu_item_rect(self, controller: Any) -> Tuple[float, float, float, float] | None:
        """Get hovered menu item rect from controller."""
        return get_menu_hover_item_rect(controller)

    def _get_hovered_top_bar_control_id(self, controller: Any) -> str | None:
        """Get hovered top bar control ID from controller."""
        from engine.editor.editor_hover_query import get_hovered_top_bar_control_id  # noqa: PLC0415

        return get_hovered_top_bar_control_id(controller)

    def _get_hovered_context_item_id(self, controller: Any) -> str | None:
        """Get hovered context menu item ID from controller."""
        from engine.editor.editor_panels_query import panels_is_open  # noqa: PLC0415

        if panels_is_open(controller, "context_menu"):
            return get_context_menu_hover_id(controller)
        return None

    def _get_hovered_context_item_rect(self, controller: Any) -> Tuple[float, float, float, float] | None:
        """Get hovered context menu item rect from controller."""
        return get_context_menu_hover_rect(controller)

    def _get_hovered_dock_tab(self, controller: Any) -> Tuple[str, str] | None:
        """Get hovered dock tab (side, name) from controller."""
        return get_hovered_dock_tab(controller)

    def _get_hovered_dock_tab_rect(self, controller: Any) -> Tuple[float, float, float, float] | None:
        """Get hovered dock tab rect from controller."""
        return get_hovered_dock_tab_rect(controller)

    def _get_hovered_splitter(self, controller: Any) -> str | None:
        """Get hovered splitter side from controller."""
        return get_hovered_splitter(controller)

    def _get_hovered_splitter_rect(self, controller: Any) -> Tuple[float, float, float, float] | None:
        """Get hovered splitter rect from controller."""
        return get_hovered_splitter_rect(controller)

    def _get_hovered_inspector_field_key(self, controller: Any) -> str | None:
        """Get hovered inspector field key from controller."""
        return get_hovered_inspector_field_key(controller)

    def _get_hovered_inspector_field_rect(self, controller: Any) -> Tuple[float, float, float, float] | None:
        """Get hovered inspector field rect from controller."""
        return get_hovered_inspector_field_rect(controller)

    def _get_hovered_entity_id(self, controller: Any) -> str | None:
        """Get hovered entity ID from controller."""
        return get_hovered_entity_id(controller)

    def _get_hovered_entity_rect(self, controller: Any) -> Tuple[float, float, float, float] | None:
        """Get hovered entity rect (world coords) from controller."""
        return get_hovered_entity_rect(controller)
