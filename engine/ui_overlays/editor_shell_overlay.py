"""Editor Shell Overlay - draws the main editor chrome/frame.

This overlay renders the editor shell UI including:
- Top bar with title, scene name, and dirty indicator
- Left dock panel with tab headers
- Right dock panel with tab headers
- Viewport border frame

Draws ONLY when editor mode is active. Renders behind other editor overlays.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import engine.optional_arcade as optional_arcade

from ..text_draw import draw_text_cached, TextCache
from .common import UIElement, draw_panel_bg

if TYPE_CHECKING:  # pragma: no cover
    from ..game import GameWindow


# Color palette for the editor shell
SHELL_BG_COLOR = (30, 30, 35, 255)
SHELL_HEADER_COLOR = (45, 45, 50, 255)
SHELL_BORDER_COLOR = (60, 60, 70, 255)
SHELL_ACCENT_COLOR = (80, 140, 200, 255)
SHELL_TEXT_COLOR = (220, 220, 220, 255)
SHELL_TEXT_DIM_COLOR = (140, 140, 140, 255)
SHELL_TAB_ACTIVE_COLOR = (70, 130, 180, 255)
SHELL_TAB_INACTIVE_COLOR = (50, 50, 55, 255)
SHELL_BUTTON_BG_COLOR = (50, 50, 55, 255)
SHELL_BUTTON_ACTIVE_COLOR = (80, 140, 200, 255)


class EditorShellOverlay(UIElement):
    """Editor-only overlay that draws the main editor shell chrome."""

    def __init__(self, window: "GameWindow") -> None:
        super().__init__(window)
        self._text_cache = TextCache(max_size=128)
        self._cached_layout: Any = None
        self._cached_size: tuple[int, int] = (0, 0)
        self._cached_dock_widths: tuple[int, int] = (320, 320)

    def on_resize(self, width: int, height: int) -> None:
        """Invalidate cached layout on resize."""
        self._cached_layout = None
        self._cached_size = (0, 0)

    def _get_dock_widths(self) -> tuple[int, int]:
        """Get effective dock widths from controller (accounting for collapse/maximize)."""
        controller = getattr(self.window, "editor_controller", None)
        if controller is None:
            return (320, 320)
        from ..editor.editor_dock_query import get_effective_dock_widths

        return get_effective_dock_widths(controller, self.window.width)

    def _get_layout(self) -> Any:
        """Get or compute the current layout."""
        from ..editor.editor_shell_layout import compute_editor_shell_layout

        size = (self.window.width, self.window.height)
        dock_widths = self._get_dock_widths()
        if (self._cached_layout is None or 
            self._cached_size != size or 
            self._cached_dock_widths != dock_widths):
            self._cached_layout = compute_editor_shell_layout(
                size[0], size[1], dock_widths[0], dock_widths[1]
            )
            self._cached_size = size
            self._cached_dock_widths = dock_widths
        return self._cached_layout

    def _get_dock_tab_state(self) -> Any:
        """Get dock tab state from controller."""
        from ..editor.editor_shell_layout import DockTabState

        controller = getattr(self.window, "editor_controller", None)
        if controller is None:
            return DockTabState()
        dock = getattr(controller, "dock", None)
        snapshot = dock.get_snapshot() if dock is not None and hasattr(dock, "get_snapshot") else dock
        left_tab = getattr(snapshot, "left_tab", "Outliner") or "Outliner"
        right_tab = getattr(snapshot, "right_tab", "Inspector") or "Inspector"
        return DockTabState(left_tab=left_tab, right_tab=right_tab)

    def draw(self) -> None:
        from ..editor.editor_dock_query import (
            get_dock_collapsed,
            get_viewport_maximized,
        )

        controller = getattr(self.window, "editor_controller", None)
        if controller is None or not getattr(controller, "active", False):
            return

        layout = self._get_layout()
        tab_state = self._get_dock_tab_state()
        cache = self._text_cache

        # Check collapse/maximize state
        left_collapsed, right_collapsed = get_dock_collapsed(controller)
        viewport_maximized = get_viewport_maximized(controller)

        self._draw_top_bar(layout, controller, cache, viewport_maximized, left_collapsed, right_collapsed)

        # Only draw docks if not maximized and not collapsed
        if not viewport_maximized:
            if not left_collapsed:
                self._draw_left_dock(layout, tab_state, cache)
            if not right_collapsed:
                self._draw_right_dock(layout, tab_state, cache)

        self._draw_viewport_frame(layout)
        # Bottom bar is handled by EditorStatusBarOverlay

    def _draw_top_bar(
        self,
        layout: Any,
        controller: object,
        cache: TextCache,
        viewport_maximized: bool = False,
        left_collapsed: bool = False,
        right_collapsed: bool = False,
    ) -> None:
        """Draw the top bar with title, scene name, dirty indicator, and dock controls."""
        from ..editor.editor_shell_layout import compute_top_bar_controls

        bar = layout.top_bar

        # Background
        draw_panel_bg(bar.left, bar.right, bar.bottom, bar.top, SHELL_BG_COLOR)

        # Header strip at bottom of top bar
        strip_height = 4.0
        draw_panel_bg(
            bar.left, bar.right,
            bar.bottom, bar.bottom + strip_height,
            SHELL_ACCENT_COLOR
        )

        # Title: "MESH EDITOR"
        title_text = "MESH EDITOR"
        if viewport_maximized:
            title_text = "MESH EDITOR [MAX]"
        draw_text_cached(
            title_text,
            bar.left + 16.0,
            bar.center_y,
            color=SHELL_TEXT_COLOR if not viewport_maximized else SHELL_ACCENT_COLOR,
            font_size=16,
            anchor_y="center",
            bold=True,
            cache=cache,
        )

        # Scene name (center)
        scene_name = self._get_scene_name(controller)
        is_dirty = getattr(controller, "scene_dirty", False)
        dirty_marker = " *" if is_dirty else ""
        scene_label = f"{scene_name}{dirty_marker}"

        draw_text_cached(
            scene_label,
            bar.center_x,
            bar.center_y,
            color=SHELL_TEXT_COLOR if not is_dirty else SHELL_ACCENT_COLOR,
            font_size=14,
            anchor_x="center",
            anchor_y="center",
            cache=cache,
        )

        # Draw dock toggle controls [L] [R] [M]
        controls = compute_top_bar_controls(layout)
        self._draw_top_bar_button(controls.toggle_left, "L", left_collapsed, cache)
        self._draw_top_bar_button(controls.toggle_right, "R", right_collapsed, cache)
        self._draw_top_bar_button(controls.toggle_max, "M", viewport_maximized, cache)

        # Right side: tool mode indicator (after the buttons)
        tool_mode = getattr(controller, "tool_mode", "MOVE")
        draw_text_cached(
            f"Tool: {tool_mode}",
            bar.right - 16.0,
            bar.center_y,
            color=SHELL_TEXT_DIM_COLOR,
            font_size=12,
            anchor_x="right",
            anchor_y="center",
            cache=cache,
        )

    def _draw_top_bar_button(self, rect: Any, label: str, is_active: bool, cache: TextCache) -> None:
        """Draw a top bar toggle button.

        Args:
            rect: Button rect.
            label: Single character label.
            is_active: Whether the toggle is active (collapsed/maximized).
            cache: Text cache.
        """
        # Background
        bg_color = SHELL_BUTTON_ACTIVE_COLOR if is_active else SHELL_BUTTON_BG_COLOR
        draw_panel_bg(rect.left, rect.right, rect.bottom, rect.top, bg_color)

        # Border
        draw_panel_bg(rect.left, rect.right, rect.bottom, rect.bottom + 1, SHELL_BORDER_COLOR)
        draw_panel_bg(rect.left, rect.right, rect.top - 1, rect.top, SHELL_BORDER_COLOR)
        draw_panel_bg(rect.left, rect.left + 1, rect.bottom, rect.top, SHELL_BORDER_COLOR)
        draw_panel_bg(rect.right - 1, rect.right, rect.bottom, rect.top, SHELL_BORDER_COLOR)

        # Label
        draw_text_cached(
            label,
            rect.center_x,
            rect.center_y,
            color=SHELL_TEXT_COLOR,
            font_size=11,
            anchor_x="center",
            anchor_y="center",
            bold=is_active,
            cache=cache,
        )

    def _draw_left_dock(self, layout: Any, tab_state: Any, cache: TextCache) -> None:
        """Draw the left dock panel with tab headers."""
        dock = layout.left_dock

        # Background
        draw_panel_bg(dock.left, dock.right, dock.bottom, dock.top, SHELL_BG_COLOR)

        # Tab header area
        tab_height = 32.0
        tab_y = dock.top - tab_height

        # Tab background
        draw_panel_bg(dock.left, dock.right, tab_y, dock.top, SHELL_HEADER_COLOR)

        # Tab buttons
        tabs = ("Project", "Scene", "Outliner")
        tab_width = dock.width / len(tabs)
        active_tab = tab_state.left_tab

        for i, tab_name in enumerate(tabs):
            tab_left = dock.left + i * tab_width
            tab_right = tab_left + tab_width
            is_active = tab_name == active_tab

            # Tab background
            tab_color = SHELL_TAB_ACTIVE_COLOR if is_active else SHELL_TAB_INACTIVE_COLOR
            draw_panel_bg(tab_left + 2, tab_right - 2, tab_y + 2, dock.top - 2, tab_color)

            # Tab label
            draw_text_cached(
                tab_name,
                (tab_left + tab_right) / 2,
                (tab_y + dock.top) / 2,
                color=SHELL_TEXT_COLOR if is_active else SHELL_TEXT_DIM_COLOR,
                font_size=11,
                anchor_x="center",
                anchor_y="center",
                cache=cache,
            )

        # Separator line
        draw_panel_bg(dock.left, dock.right, tab_y - 1, tab_y, SHELL_BORDER_COLOR)

        # Right edge border
        draw_panel_bg(dock.right - 1, dock.right, dock.bottom, dock.top, SHELL_BORDER_COLOR)

    def _draw_right_dock(self, layout: Any, tab_state: Any, cache: TextCache) -> None:
        """Draw the right dock panel with tab headers."""
        dock = layout.right_dock

        # Background
        draw_panel_bg(dock.left, dock.right, dock.bottom, dock.top, SHELL_BG_COLOR)

        # Tab header area
        tab_height = 32.0
        tab_y = dock.top - tab_height

        # Tab background
        draw_panel_bg(dock.left, dock.right, tab_y, dock.top, SHELL_HEADER_COLOR)

        # Tab buttons
        tabs = ("Inspector", "Assets", "Items", "History", "Problems", "Debug")
        tab_width = dock.width / len(tabs)
        active_tab = tab_state.right_tab

        for i, tab_name in enumerate(tabs):
            tab_left = dock.left + i * tab_width
            tab_right = tab_left + tab_width
            is_active = tab_name == active_tab

            # Tab background
            tab_color = SHELL_TAB_ACTIVE_COLOR if is_active else SHELL_TAB_INACTIVE_COLOR
            draw_panel_bg(tab_left + 2, tab_right - 2, tab_y + 2, dock.top - 2, tab_color)

            # Tab label
            draw_text_cached(
                tab_name,
                (tab_left + tab_right) / 2,
                (tab_y + dock.top) / 2,
                color=SHELL_TEXT_COLOR if is_active else SHELL_TEXT_DIM_COLOR,
                font_size=11,
                anchor_x="center",
                anchor_y="center",
                cache=cache,
            )

        # Separator line
        draw_panel_bg(dock.left, dock.right, tab_y - 1, tab_y, SHELL_BORDER_COLOR)

        # Left edge border
        draw_panel_bg(dock.left, dock.left + 1, dock.bottom, dock.top, SHELL_BORDER_COLOR)

    def _draw_viewport_frame(self, layout: Any) -> None:
        """Draw a subtle frame around the viewport area."""
        vp = layout.viewport

        # Draw border lines around viewport
        border_color = SHELL_BORDER_COLOR

        # Top border
        draw_panel_bg(vp.left, vp.right, vp.top - 1, vp.top, border_color)
        # Bottom border
        draw_panel_bg(vp.left, vp.right, vp.bottom, vp.bottom + 1, border_color)

    def _get_scene_name(self, controller: object) -> str:
        """Extract the current scene name from controller state."""
        # Try to get from scene controller
        scene_controller = getattr(self.window, "scene_controller", None)
        if scene_controller:
            scene_id = getattr(scene_controller, "current_scene_id", None)
            if scene_id:
                return str(scene_id)

        # Fallback to loaded scene data
        loaded_data = getattr(scene_controller, "_loaded_scene_data", None) if scene_controller else None
        if isinstance(loaded_data, dict):
            scene_name = loaded_data.get("name") or loaded_data.get("id")
            if scene_name:
                return str(scene_name)

        return "<No Scene>"
