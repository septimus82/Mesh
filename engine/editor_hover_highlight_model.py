"""Pure module for hover highlight computation.

This module provides deterministic, headless-safe functions for computing
hover highlight rectangles for editor UI elements. No arcade dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Tuple

from engine.editor.editor_modal_state_query import (
    is_scene_browser_active,
    is_unsaved_changes_pending,
)
from engine.editor.editor_session_query import get_session_snapshot


class HoverHighlightKind(str, Enum):
    """Kind of hover highlight target."""

    MENU_TITLE = "menu_title"
    MENU_ITEM = "menu_item"
    CONTEXT_ITEM = "context_item"
    TOPBAR_CONTROL = "topbar_control"
    DOCK_TAB = "dock_tab"
    SPLITTER = "splitter"
    INSPECTOR_FIELD = "inspector_field"
    ENTITY_HOVER = "entity_hover"


@dataclass(frozen=True, slots=True)
class HighlightRect:
    """Rectangle for hover highlight rendering.

    Attributes:
        x: Left edge x-coordinate.
        y: Bottom edge y-coordinate.
        w: Width.
        h: Height.
    """

    x: float
    y: float
    w: float
    h: float

    @property
    def left(self) -> float:
        """Left edge x-coordinate."""
        return self.x

    @property
    def right(self) -> float:
        """Right edge x-coordinate."""
        return self.x + self.w

    @property
    def bottom(self) -> float:
        """Bottom edge y-coordinate."""
        return self.y

    @property
    def top(self) -> float:
        """Top edge y-coordinate."""
        return self.y + self.h

    def contains_point(self, px: float, py: float) -> bool:
        """Check if point is inside rectangle.

        Args:
            px: Point x-coordinate.
            py: Point y-coordinate.

        Returns:
            True if point is inside or on edge.
        """
        return self.left <= px <= self.right and self.bottom <= py <= self.top

    def clamped(self, window_w: int, window_h: int) -> "HighlightRect":
        """Return a new rect clamped to window bounds.

        Args:
            window_w: Window width.
            window_h: Window height.

        Returns:
            New HighlightRect clamped to [0, window_w] x [0, window_h].
        """
        x = max(0.0, min(self.x, float(window_w)))
        y = max(0.0, min(self.y, float(window_h)))
        right = max(0.0, min(self.x + self.w, float(window_w)))
        top = max(0.0, min(self.y + self.h, float(window_h)))
        return HighlightRect(x=x, y=y, w=right - x, h=top - y)


@dataclass(frozen=True, slots=True)
class HoverHighlightSpec:
    """Specification for a hover highlight to render.

    Attributes:
        kind: Type of highlight target.
        rect: Rectangle in screen/UI coordinates (or world for entity).
        label: Optional label for debugging/tooltips.
        is_world_space: True if rect is in world coordinates (entity hover).
    """

    kind: HoverHighlightKind
    rect: HighlightRect
    label: str | None = None
    is_world_space: bool = False


# Priority order for highlight kinds (lower index = higher priority)
_PRIORITY_ORDER = [
    HoverHighlightKind.CONTEXT_ITEM,
    HoverHighlightKind.MENU_ITEM,
    HoverHighlightKind.MENU_TITLE,
    HoverHighlightKind.TOPBAR_CONTROL,
    HoverHighlightKind.SPLITTER,
    HoverHighlightKind.DOCK_TAB,
    HoverHighlightKind.INSPECTOR_FIELD,
    HoverHighlightKind.ENTITY_HOVER,
]

TOPBAR_CONTROL_LABELS = {
    "L": "Toggle Left Dock",
    "R": "Toggle Right Dock",
    "M": "Maximize Viewport",
}


def _kind_priority(kind: HoverHighlightKind) -> int:
    """Get priority index for a highlight kind (lower = higher priority)."""
    try:
        return _PRIORITY_ORDER.index(kind)
    except ValueError:
        return 999


def resolve_hover_highlights(
    *,
    window_w: int,
    window_h: int,
    # Menu bar state
    hovered_menu_title: str | None,
    hovered_menu_title_rect: Tuple[float, float, float, float] | None,
    hovered_menu_item_id: str | None,
    hovered_menu_item_rect: Tuple[float, float, float, float] | None,
    # Top bar control hover state
    hovered_top_bar_control_id: str | None,
    # Context menu state
    hovered_context_item_id: str | None,
    hovered_context_item_rect: Tuple[float, float, float, float] | None,
    # Dock tab state
    hovered_dock_tab: Tuple[str, str] | None,  # ("left"/"right", tab_name)
    hovered_dock_tab_rect: Tuple[float, float, float, float] | None,
    # Splitter state
    hovered_splitter: str | None,  # "left"/"right"/None
    hovered_splitter_rect: Tuple[float, float, float, float] | None,
    # Inspector field state
    hovered_inspector_field_key: str | None,
    hovered_inspector_field_rect: Tuple[float, float, float, float] | None,
    # Entity hover state (world coordinates)
    hovered_entity_id: str | None,
    hovered_entity_rect: Tuple[float, float, float, float] | None,
    # Block flag
    block_ui: bool,
) -> Tuple[HoverHighlightSpec, ...]:
    """Resolve hover highlights based on current editor state.

    Priority order (highest first):
    1. Context menu item
    2. Menu bar item
    3. Menu bar title
    4. Top bar control
    5. Splitter
    6. Dock tab
    7. Inspector field
    8. Hovered entity

    Args:
        window_w: Window width for clamping.
        window_h: Window height for clamping.
        hovered_menu_title: Hovered menu title (e.g., "File") or None.
        hovered_menu_title_rect: Rect tuple (x, y, w, h) for menu title.
        hovered_menu_item_id: Hovered menu item ID or None.
        hovered_menu_item_rect: Rect tuple for menu item.
        hovered_top_bar_control_id: Hovered top bar control ID ("L", "R", "M") or None.
        hovered_context_item_id: Hovered context menu item ID or None.
        hovered_context_item_rect: Rect tuple for context item.
        hovered_dock_tab: Tuple of ("left"/"right", tab_name) or None.
        hovered_dock_tab_rect: Rect tuple for dock tab.
        hovered_splitter: "left", "right", or None.
        hovered_splitter_rect: Rect tuple for splitter.
        hovered_inspector_field_key: Hovered inspector field key or None.
        hovered_inspector_field_rect: Rect tuple for inspector field.
        hovered_entity_id: Hovered entity ID or None.
        hovered_entity_rect: Rect tuple for entity bounds (world coords).
        block_ui: If True, return empty (modal/text input active).

    Returns:
        Tuple of HoverHighlightSpec in priority order (highest first).
        Rects are clamped to window bounds (except world-space entities).
    """
    if block_ui:
        return ()

    specs: list[HoverHighlightSpec] = []

    # Helper to create clamped rect
    def make_rect(r: Tuple[float, float, float, float] | None, clamp: bool = True) -> HighlightRect | None:
        if r is None:
            return None
        rect = HighlightRect(x=r[0], y=r[1], w=r[2], h=r[3])
        if clamp:
            return rect.clamped(window_w, window_h)
        return rect

    # Context menu item (highest priority)
    if hovered_context_item_id is not None:
        rect = make_rect(hovered_context_item_rect)
        if rect is not None:
            specs.append(HoverHighlightSpec(
                kind=HoverHighlightKind.CONTEXT_ITEM,
                rect=rect,
                label=hovered_context_item_id,
            ))

    # Menu item
    if hovered_menu_item_id is not None:
        rect = make_rect(hovered_menu_item_rect)
        if rect is not None:
            specs.append(HoverHighlightSpec(
                kind=HoverHighlightKind.MENU_ITEM,
                rect=rect,
                label=hovered_menu_item_id,
            ))

    # Menu title
    if hovered_menu_title is not None:
        rect = make_rect(hovered_menu_title_rect)
        if rect is not None:
            specs.append(HoverHighlightSpec(
                kind=HoverHighlightKind.MENU_TITLE,
                rect=rect,
                label=hovered_menu_title,
            ))

    # Top bar controls
    if hovered_top_bar_control_id is not None:
        from engine.editor.editor_shell_layout import (
            compute_editor_shell_layout,
            compute_top_bar_controls,
        )

        layout = compute_editor_shell_layout(window_w, window_h)
        controls = compute_top_bar_controls(layout)
        control_rect = None
        if hovered_top_bar_control_id == "L":
            control_rect = controls.toggle_left
        elif hovered_top_bar_control_id == "R":
            control_rect = controls.toggle_right
        elif hovered_top_bar_control_id == "M":
            control_rect = controls.toggle_max

        if control_rect is not None:
            rect = make_rect(
                (control_rect.left, control_rect.bottom, control_rect.width, control_rect.height)
            )
            if rect is not None:
                specs.append(HoverHighlightSpec(
                    kind=HoverHighlightKind.TOPBAR_CONTROL,
                    rect=rect,
                    label=TOPBAR_CONTROL_LABELS.get(hovered_top_bar_control_id, hovered_top_bar_control_id),
                ))

    # Splitter
    if hovered_splitter is not None:
        rect = make_rect(hovered_splitter_rect)
        if rect is not None:
            specs.append(HoverHighlightSpec(
                kind=HoverHighlightKind.SPLITTER,
                rect=rect,
                label=f"{hovered_splitter}_splitter",
            ))

    # Dock tab
    if hovered_dock_tab is not None:
        rect = make_rect(hovered_dock_tab_rect)
        if rect is not None:
            side, tab = hovered_dock_tab
            specs.append(HoverHighlightSpec(
                kind=HoverHighlightKind.DOCK_TAB,
                rect=rect,
                label=f"{side}_{tab}",
            ))

    # Inspector field
    if hovered_inspector_field_key is not None:
        rect = make_rect(hovered_inspector_field_rect)
        if rect is not None:
            specs.append(HoverHighlightSpec(
                kind=HoverHighlightKind.INSPECTOR_FIELD,
                rect=rect,
                label=hovered_inspector_field_key,
            ))

    # Entity hover (world space, no clamping)
    if hovered_entity_id is not None:
        rect = make_rect(hovered_entity_rect, clamp=False)
        if rect is not None:
            specs.append(HoverHighlightSpec(
                kind=HoverHighlightKind.ENTITY_HOVER,
                rect=rect,
                label=hovered_entity_id,
                is_world_space=True,
            ))

    # Sort by priority (stable sort preserves insertion order for equal priority)
    specs.sort(key=lambda s: _kind_priority(s.kind))

    return tuple(specs)


def is_ui_blocked(controller: Any) -> bool:
    """Check if UI hover highlights should be blocked.

    Blocks during text input or modal dialogs.

    Args:
        controller: The editor controller.

    Returns:
        True if hover highlights should be blocked.
    """
    get_session_snapshot(controller)
    # Text input modes
    if getattr(controller, "palette_filter_active", False):
        return True
    if getattr(controller, "hierarchy_filter_active", False):
        return True
    if getattr(controller, "hierarchy_rename_active", False):
        return True
    if getattr(controller, "animation_edit_active", False):
        return True
    if getattr(controller, "inspector_edit_active", False):
        return True
    from engine.editor.editor_panels_query import panels_is_open  # noqa: PLC0415

    if panels_is_open(controller, "command_palette"):
        return True
    if getattr(controller, "entity_panels_filter_active", False):
        return True
    if getattr(controller, "scene_browser_filter_active", False):
        return True
    if getattr(controller, "asset_browser_filter_active", False):
        return True

    # Modal states
    if is_unsaved_changes_pending(controller):
        return True
    if is_scene_browser_active(controller):
        return True

    return False
