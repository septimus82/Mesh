"""Menu bar model for the editor.

This module provides pure dataclasses and functions for computing the
menu bar layout and handling hit testing. No rendering or state
management - just deterministic geometry computation.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from engine.editor.editor_actions import get_editor_actions

# Layout constants
MENU_BAR_HEIGHT = 24
MENU_TITLE_PADDING_X = 12
MENU_ITEM_HEIGHT = 24
MENU_ITEM_PADDING_X = 16
MENU_DROPDOWN_WIDTH = 200
MENU_FONT_SIZE = 12

MENU_GROUP_ORDER: tuple[str, ...] = ("File", "Edit", "View", "Scene")

MENU_ACTION_ORDER: dict[str, tuple[str, ...]] = {
    "File": (
        "editor.scene.save",
        "editor.scene_browser.open",
        "|",
        "app.export_web_demo",
        "|",
        "app.quit",
    ),
    "Edit": (
        "editor.history.undo",
        "editor.history.redo",
        "|",
        "editor.duplicate",
        "editor.delete",
    ),
    "View": (
        "editor.panel.project_explorer.toggle",
        "editor.panel.outliner.toggle",
        "editor.panel.inspector.toggle",
        "editor.panel.history.toggle",
        "editor.panel.problems.toggle",
        "editor.panel.debug.toggle",
        "|",
        "editor.problems.jump_to_selected",
        "editor.problems.copy_location",
        "|",
        "editor.panel.prefab_variant_editor.toggle",
        "|",
        "editor.entity_panels.toggle",
        "editor.asset_browser.toggle",
        "editor.scene_browser.toggle",
        "|",
        "editor.command_palette.toggle",
        "|",
        "editor.ghost_originals.toggle",
        "|",
        "editor.hd2d.preset.soft.apply",
        "editor.hd2d.preset.crisp.apply",
        "editor.hd2d.preset.noir.apply",
        "editor.hd2d.preset.dreamy.apply",
    ),
        "Scene": (
            "editor.prefab_palette.toggle",
            "editor.light_tool.toggle",
            "editor.occluder_tool.toggle",
            "|",
            "editor.background_planes.add",
            "editor.background_planes.duplicate",
            "editor.background_planes.remove",
            "|",
            "editor.background_planes.move_up",
            "editor.background_planes.move_down",
            "editor.background_planes.select_prev",
            "editor.background_planes.select_next",
            "|",
            "editor.background_planes.toggle_repeat_x",
            "editor.background_planes.toggle_repeat_y",
        ),
}


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
    actions = get_editor_actions(controller, window)
    action_map = {action.id: action for action in actions}

    groups: list[MenuGroup] = []
    def _action_allowed(action_id: str) -> bool:
        action = action_map.get(action_id)
        if action is None or not action.in_menu:
            return False
        if is_web and action.id in {"app.export_web_demo", "app.quit"}:
            return False
        return True

    def _has_future_action(entries: tuple[str, ...]) -> bool:
        for entry in entries:
            if entry == "|":
                continue
            if _action_allowed(entry):
                return True
        return False

    for group in MENU_GROUP_ORDER:
        order = MENU_ACTION_ORDER.get(group, ())
        items: list[MenuItem] = []
        sep_index = 0
        for idx, entry in enumerate(order):
            if entry == "|":
                if not items:
                    continue
                if not _has_future_action(order[idx + 1 :]):
                    continue
                if items and items[-1].label == "-":
                    continue
                sep_index += 1
                items.append(MenuItem(id=f"{group.lower()}_separator_{sep_index}", label="-", enabled=False))
                continue
            if not _action_allowed(entry):
                continue
            action = action_map.get(entry)
            if action is None:
                continue
            enabled = action.enabled(controller, window)
            label = action.menu_label or action.title
            items.append(MenuItem(id=action.id, label=label, enabled=enabled, shortcut=action.shortcut))
        groups.append(MenuGroup(title=group, items=tuple(items)))

    return groups


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
