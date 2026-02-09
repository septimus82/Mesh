"""Context menu model for Project Explorer.

Pure helpers for deterministic, action-driven context menus.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple, Literal

# Layout constants
CONTEXT_MENU_WIDTH = 200
CONTEXT_MENU_ITEM_HEIGHT = 24
CONTEXT_MENU_PADDING_X = 12
CONTEXT_MENU_PADDING_Y = 4
CONTEXT_MENU_FONT_SIZE = 12
CONTEXT_MENU_BG_COLOR = (40, 40, 45, 255)
CONTEXT_MENU_BORDER_COLOR = (80, 80, 90, 255)
CONTEXT_MENU_HOVER_COLOR = (60, 60, 70, 255)
CONTEXT_MENU_TEXT_COLOR = (220, 220, 220, 255)
CONTEXT_MENU_DISABLED_TEXT_COLOR = (120, 120, 130, 255)

@dataclass(frozen=True, slots=True)
class ContextMenuItem:
    """A single item in the context menu."""
    kind: Literal["action", "separator"]
    action_id: Optional[str]
    title: Optional[str]
    enabled: bool
    shortcut_text: Optional[str] = None

@dataclass(frozen=True, slots=True)
class ProjectExplorerSelectionPayload:
    """Relevant selection state for computing menu items."""
    selection_count: int
    has_common_parent: bool
    can_rename: bool
    can_move: bool
    can_delete: bool
    can_reveal: bool
    can_copy_paths: bool
    can_copy_common_parent: bool
    can_select_all: bool
    can_clear_selection: bool
    can_invert_selection: bool


def _action_item(
    action_id: str,
    title: str,
    enabled: bool,
    shortcut_text: Optional[str],
) -> ContextMenuItem:
    return ContextMenuItem(
        kind="action",
        action_id=action_id,
        title=title,
        enabled=bool(enabled),
        shortcut_text=shortcut_text,
    )


def _separator() -> ContextMenuItem:
    return ContextMenuItem(
        kind="separator",
        action_id=None,
        title=None,
        enabled=False,
        shortcut_text=None,
    )


def _shortcut_for_action(
    action_id: str,
    actions_registry: Iterable[object],
    active_scopes: Iterable[str],
) -> Optional[str]:
    from engine.editor.shortcut_resolver_model import normalize_shortcut_text
    from engine.editor.editor_actions import SHORTCUT_SCOPE_GLOBAL  # noqa: PLC0415

    action = None
    for item in actions_registry:
        if str(getattr(item, "id", "")) == action_id:
            action = item
            break
    if action is None:
        return None
    shortcut = normalize_shortcut_text(getattr(action, "shortcut", "") or "")
    if not shortcut:
        return None
    scope = getattr(action, "shortcut_scope", SHORTCUT_SCOPE_GLOBAL)
    active = tuple(str(s) for s in active_scopes)
    if scope not in active:
        return None
    return shortcut

def build_project_explorer_context_menu(
    payload: ProjectExplorerSelectionPayload,
    actions_registry: Iterable[object],
    active_scopes: Iterable[str],
) -> List[ContextMenuItem]:
    """Build deterministic context menu items for Project Explorer."""
    items: List[ContextMenuItem] = []

    def add_action(action_id: str, title: str, enabled: bool) -> None:
        shortcut = _shortcut_for_action(action_id, actions_registry, active_scopes)
        items.append(_action_item(action_id, title, enabled, shortcut))

    # Group A: Rename / Move / Delete
    add_action(
        "editor.project_explorer.safe_rename_asset",
        "Rename...",
        payload.can_rename,
    )
    add_action(
        "editor.project_explorer.refactor_move_selected",
        "Move...",
        payload.can_move,
    )
    add_action(
        "editor.project_explorer.refactor_delete_selected",
        "Delete",
        payload.can_delete,
    )

    items.append(_separator())

    # Group D/E/F: Reveal + Copy actions
    add_action(
        "editor.project_explorer.reveal_current",
        "Reveal Current",
        payload.can_reveal,
    )
    add_action(
        "editor.project_explorer.copy_path",
        "Copy Path(s)",
        payload.can_copy_paths,
    )
    add_action(
        "editor.project_explorer.copy_common_parent",
        "Copy Common Parent",
        payload.can_copy_common_parent,
    )

    items.append(_separator())

    # Group G: Selection actions
    add_action(
        "editor.project_explorer.select_all",
        "Select All",
        payload.can_select_all,
    )
    add_action(
        "editor.project_explorer.clear_selection",
        "Clear Selection",
        payload.can_clear_selection,
    )
    add_action(
        "editor.project_explorer.invert_selection",
        "Invert Selection",
        payload.can_invert_selection,
    )

    # Trim leading/trailing separators and collapse duplicates deterministically
    trimmed: list[ContextMenuItem] = []
    for item in items:
        if item.kind == "separator":
            if not trimmed or trimmed[-1].kind == "separator":
                continue
        trimmed.append(item)
    while trimmed and trimmed[-1].kind == "separator":
        trimmed.pop()
    return trimmed

def clamp_menu_position(
    x: int, 
    y: int, 
    menu_w: int, 
    menu_h: int, 
    viewport_w: int, 
    viewport_h: int
) -> Tuple[int, int]:
    """Clamp menu position to keep it fully within viewport.
    
    Prefers (x, y) but shifts left/up if needed.
    """
    final_x = x
    final_y = y
    
    # Clamp X (prevent going off right)
    if final_x + menu_w > viewport_w:
        final_x = max(0, viewport_w - menu_w)
        
    # Clamp Y (prevent going off bottom)
    # Usually menus open "down", but if near bottom, maybe open "up"?
    # For simplicity v1: just shift up.
    if final_y + menu_h > viewport_h:
        final_y = max(0, viewport_h - menu_h)
        
    return (int(final_x), int(final_y))

def hit_test_menu_item(
    rel_x: float, 
    rel_y: float, 
    item_count: int
) -> Optional[int]:
    """Determine which item index is at the relative coordinates.
    
    Args:
        rel_x: local x within menu rect
        rel_y: local y within menu rect
        item_count: number of items
        
    Returns:
        Index of item, or None if out of bounds/padding.
    """
    if rel_x < 0 or rel_x > CONTEXT_MENU_WIDTH:
        return None
        
    # Skip vertical padding
    content_y = rel_y - CONTEXT_MENU_PADDING_Y
    if content_y < 0:
        return None
        
    index = int(content_y // CONTEXT_MENU_ITEM_HEIGHT)
    
    if 0 <= index < item_count:
        return index
        
    return None


def clamp_menu_index(index: int, items: List[ContextMenuItem]) -> int:
    if not items:
        return 0
    return max(0, min(int(index), len(items) - 1))


def find_index_by_action_id(items: List[ContextMenuItem], action_id: str | None) -> int | None:
    if not items or not action_id:
        return None
    for idx, item in enumerate(items):
        if item.kind != "action":
            continue
        if not item.enabled:
            continue
        if item.action_id == action_id:
            return idx
    return None


def first_selectable_index(items: List[ContextMenuItem]) -> int | None:
    """Return the first enabled non-separator item, or None if none enabled."""
    if not items:
        return None
    for idx, item in enumerate(items):
        if item.kind != "separator" and item.enabled:
            return idx
    return None


def next_selectable_index(items: List[ContextMenuItem], start: int | None, delta: int) -> int | None:
    if not items:
        return None
    if start is None:
        return first_selectable_index(items)
    idx = clamp_menu_index(start, items)
    step = 1 if delta >= 0 else -1
    remaining = len(items)
    while remaining > 0:
        idx = clamp_menu_index(idx + step, items)
        item = items[idx]
        if item.kind != "separator" and item.enabled:
            return idx
        remaining -= 1
    return None
