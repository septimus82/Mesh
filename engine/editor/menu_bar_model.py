"""Menu bar model for the editor.

This module provides pure dataclasses and functions for computing the
menu bar layout and handling hit testing. No rendering or state
management - just deterministic geometry computation.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


# Layout constants
MENU_BAR_HEIGHT = 24
MENU_TITLE_PADDING_X = 12
MENU_ITEM_HEIGHT = 24
MENU_ITEM_PADDING_X = 16
MENU_DROPDOWN_WIDTH = 200
MENU_FONT_SIZE = 12


def _is_web_runtime() -> bool:
    """Check if running in web/emscripten environment."""
    return sys.platform == "emscripten" or os.environ.get("PYGBAG") == "1"


@dataclass(frozen=True, slots=True)
class MenuRect:
    """A simple rectangle for menu hit testing."""

    x: float
    y: float
    w: float
    h: float

    def contains_point(self, px: float, py: float) -> bool:
        """Check if point is inside rectangle."""
        return self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h


@dataclass(frozen=True, slots=True)
class MenuItem:
    """A single menu item."""

    id: str
    label: str
    enabled: bool = True
    shortcut: str = ""


@dataclass(frozen=True, slots=True)
class MenuGroup:
    """A menu group with title and items."""

    title: str
    items: Tuple[MenuItem, ...]


@dataclass(frozen=True, slots=True)
class MenuBarLayout:
    """Computed layout for the menu bar."""

    titles: Dict[str, MenuRect]
    dropdown: List[Tuple[MenuItem, MenuRect]] | None
    active_menu: str | None
    bar_rect: MenuRect


def build_menu_groups(controller: Any, window: Any) -> List[MenuGroup]:
    """Build the menu groups based on current editor state.

    Args:
        controller: The editor controller.
        window: The game window.

    Returns:
        List of MenuGroup with items enabled/disabled appropriately.
    """
    is_web = _is_web_runtime()

    # Check if various editor features are available
    has_selection = getattr(controller, "selected_entity", None) is not None
    can_undo = bool(getattr(controller, "undo_stack", []))
    can_redo = bool(getattr(controller, "redo_stack", []))
    scene_dirty = getattr(controller, "scene_dirty", False)

    # File menu
    file_items: List[MenuItem] = [
        MenuItem(id="file_save_scene", label="Save Scene", enabled=scene_dirty, shortcut="Ctrl+S"),
        MenuItem(id="file_open_scene_browser", label="Open Scene...", enabled=True, shortcut="Ctrl+O"),
        MenuItem(id="file_separator_1", label="-", enabled=False),
    ]

    # Add export option (disabled on web)
    if not is_web:
        file_items.append(MenuItem(id="file_export_web_demo", label="Export Web Demo...", enabled=True))
        file_items.append(MenuItem(id="file_separator_2", label="-", enabled=False))
        file_items.append(MenuItem(id="file_quit", label="Quit", enabled=True, shortcut="Alt+F4"))

    file_menu = MenuGroup(title="File", items=tuple(file_items))

    # Edit menu
    edit_items: List[MenuItem] = [
        MenuItem(id="edit_undo", label="Undo", enabled=can_undo, shortcut="Ctrl+Z"),
        MenuItem(id="edit_redo", label="Redo", enabled=can_redo, shortcut="Ctrl+Y"),
        MenuItem(id="edit_separator_1", label="-", enabled=False),
        MenuItem(id="edit_duplicate", label="Duplicate", enabled=has_selection, shortcut="Ctrl+D"),
        MenuItem(id="edit_delete", label="Delete", enabled=has_selection, shortcut="Del"),
    ]
    edit_menu = MenuGroup(title="Edit", items=tuple(edit_items))

    # View menu
    view_items: List[MenuItem] = [
        MenuItem(id="view_toggle_entity_panels", label="Entity Panels", enabled=True, shortcut="E"),
        MenuItem(id="view_toggle_asset_browser", label="Asset Browser", enabled=True, shortcut="A"),
        MenuItem(id="view_toggle_scene_browser", label="Scene Browser", enabled=True),
        MenuItem(id="view_separator_1", label="-", enabled=False),
        MenuItem(id="view_toggle_command_palette", label="Command Palette", enabled=True, shortcut="F1"),
        MenuItem(id="view_separator_2", label="-", enabled=False),
        MenuItem(id="view_toggle_ghost_originals", label="Ghost Originals During Alt-Dup", enabled=True),
    ]
    view_menu = MenuGroup(title="View", items=tuple(view_items))

    # Scene menu
    scene_items: List[MenuItem] = [
        MenuItem(id="scene_toggle_palette", label="Prefab Palette", enabled=True, shortcut="P"),
        MenuItem(id="scene_toggle_lights", label="Lights Tool", enabled=True, shortcut="L"),
        MenuItem(id="scene_toggle_occluders", label="Occluders Tool", enabled=True, shortcut="O"),
    ]
    scene_menu = MenuGroup(title="Scene", items=tuple(scene_items))

    return [file_menu, edit_menu, view_menu, scene_menu]


def compute_menu_bar_layout(
    window_width: int,
    window_height: int,
    menu_groups: List[MenuGroup],
    active_menu: str | None,
    max_items: int = 12,
) -> MenuBarLayout:
    """Compute the menu bar layout.

    Args:
        window_width: Window width in pixels.
        window_height: Window height in pixels.
        menu_groups: List of menu groups.
        active_menu: Currently active menu title, or None.
        max_items: Maximum items to show in dropdown.

    Returns:
        MenuBarLayout with all rectangles computed.
    """
    # Menu bar is at the top of the window
    bar_y = window_height - MENU_BAR_HEIGHT
    bar_rect = MenuRect(x=0, y=bar_y, w=float(window_width), h=MENU_BAR_HEIGHT)

    # Compute title rectangles
    titles: Dict[str, MenuRect] = {}
    current_x = MENU_TITLE_PADDING_X

    for group in menu_groups:
        # Estimate title width (roughly 8 pixels per character)
        title_width = len(group.title) * 8 + MENU_TITLE_PADDING_X * 2
        titles[group.title] = MenuRect(
            x=current_x,
            y=bar_y,
            w=title_width,
            h=MENU_BAR_HEIGHT,
        )
        current_x += title_width

    # Compute dropdown if a menu is active
    dropdown: List[Tuple[MenuItem, MenuRect]] | None = None
    if active_menu:
        for group in menu_groups:
            if group.title == active_menu:
                dropdown = []
                title_rect = titles.get(active_menu)
                if title_rect:
                    dropdown_x = title_rect.x
                    dropdown_y = bar_y - MENU_ITEM_HEIGHT  # Start below the bar

                    for i, item in enumerate(group.items[:max_items]):
                        if item.label == "-":
                            # Separator has reduced height
                            item_rect = MenuRect(
                                x=dropdown_x,
                                y=dropdown_y,
                                w=MENU_DROPDOWN_WIDTH,
                                h=8,
                            )
                            dropdown_y -= 8
                        else:
                            item_rect = MenuRect(
                                x=dropdown_x,
                                y=dropdown_y,
                                w=MENU_DROPDOWN_WIDTH,
                                h=MENU_ITEM_HEIGHT,
                            )
                            dropdown_y -= MENU_ITEM_HEIGHT
                        dropdown.append((item, item_rect))
                break

    return MenuBarLayout(
        titles=titles,
        dropdown=dropdown,
        active_menu=active_menu,
        bar_rect=bar_rect,
    )


def hit_test_menu_title(x: float, y: float, layout: MenuBarLayout) -> str | None:
    """Test if a point hits a menu title.

    Args:
        x: Screen X coordinate.
        y: Screen Y coordinate.
        layout: The menu bar layout.

    Returns:
        Menu title if hit, None otherwise.
    """
    for title, rect in layout.titles.items():
        if rect.contains_point(x, y):
            return title
    return None


def hit_test_menu_item(x: float, y: float, layout: MenuBarLayout) -> str | None:
    """Test if a point hits a menu item.

    Args:
        x: Screen X coordinate.
        y: Screen Y coordinate.
        layout: The menu bar layout.

    Returns:
        Item ID if hit, None otherwise.
    """
    if layout.dropdown is None:
        return None

    for item, rect in layout.dropdown:
        if item.label != "-" and rect.contains_point(x, y):
            return item.id
    return None


def hit_test_menu_bar(x: float, y: float, layout: MenuBarLayout) -> bool:
    """Test if a point is within the menu bar area.

    Args:
        x: Screen X coordinate.
        y: Screen Y coordinate.
        layout: The menu bar layout.

    Returns:
        True if point is in menu bar area.
    """
    return layout.bar_rect.contains_point(x, y)


def get_dropdown_bounds(layout: MenuBarLayout) -> MenuRect | None:
    """Get the bounding rectangle of the dropdown menu.

    Args:
        layout: The menu bar layout.

    Returns:
        Bounding rectangle, or None if no dropdown.
    """
    if not layout.dropdown:
        return None

    min_x = float("inf")
    max_x = float("-inf")
    min_y = float("inf")
    max_y = float("-inf")

    for _, rect in layout.dropdown:
        min_x = min(min_x, rect.x)
        max_x = max(max_x, rect.x + rect.w)
        min_y = min(min_y, rect.y)
        max_y = max(max_y, rect.y + rect.h)

    return MenuRect(x=min_x, y=min_y, w=max_x - min_x, h=max_y - min_y)
