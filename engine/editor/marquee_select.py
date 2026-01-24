"""Pure module for marquee box selection computation.

This module provides deterministic, headless-safe functions for computing
marquee selection rectangles and entity intersection. No arcade dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from .selection_outline import RectF


@dataclass(frozen=True, slots=True)
class MarqueeState:
    """State of an active marquee selection drag.

    Attributes:
        active: Whether marquee is currently being dragged.
        start_world: Start point in world coordinates (click position).
        end_world: Current end point in world coordinates (drag position).
        shift: Whether Shift modifier was held at start.
    """

    active: bool
    start_world: Tuple[float, float]
    end_world: Tuple[float, float]
    shift: bool


def rect_from_points(p1: Tuple[float, float], p2: Tuple[float, float]) -> RectF:
    """Create a RectF from two corner points, normalizing to positive width/height.

    Args:
        p1: First point (x, y).
        p2: Second point (x, y).

    Returns:
        RectF with x,y as bottom-left and positive w,h.
    """
    x1, y1 = p1
    x2, y2 = p2

    min_x = min(x1, x2)
    max_x = max(x1, x2)
    min_y = min(y1, y2)
    max_y = max(y1, y2)

    return RectF(x=min_x, y=min_y, w=max_x - min_x, h=max_y - min_y)


def rect_intersects(a: RectF, b: RectF) -> bool:
    """Check if two rectangles intersect (inclusive edges).

    Args:
        a: First rectangle.
        b: Second rectangle.

    Returns:
        True if rectangles overlap or touch.
    """
    # No intersection if one is completely to the left/right/above/below the other
    if a.right < b.left or b.right < a.left:
        return False
    if a.top < b.bottom or b.top < a.bottom:
        return False
    return True


def compute_marquee_candidates(
    marquee_rect: RectF,
    entity_bounds: list[Tuple[str, RectF]],
) -> list[str]:
    """Compute entity IDs whose bounds intersect the marquee rectangle.

    Args:
        marquee_rect: The marquee selection rectangle.
        entity_bounds: List of (entity_id, bounds_rect) tuples.

    Returns:
        List of entity IDs that intersect marquee, sorted by entity_id for determinism.
    """
    candidates: list[str] = []

    for entity_id, bounds in entity_bounds:
        if rect_intersects(marquee_rect, bounds):
            candidates.append(entity_id)

    # Sort for deterministic ordering
    candidates.sort()
    return candidates


def apply_marquee_selection(
    current_selected_ids: list[str],
    marquee_ids: list[str],
    shift: bool,
) -> list[str]:
    """Apply marquee selection with optional shift-toggle behavior.

    Args:
        current_selected_ids: Currently selected entity IDs.
        marquee_ids: Entity IDs selected by marquee (already sorted).
        shift: If True, toggle selection; if False, replace selection.

    Returns:
        New selection list in deterministic order.
    """
    if not shift:
        # Replace: just return the marquee selection (already sorted)
        return list(marquee_ids)

    # Shift-toggle: toggle each marquee entity in current selection
    current_set = set(current_selected_ids)
    marquee_set = set(marquee_ids)

    # Find items to remove (in both) and items to add (in marquee but not current)
    to_remove = current_set & marquee_set
    to_add = marquee_set - current_set

    # Build result: keep current items not being removed, in original order
    result: list[str] = []
    for eid in current_selected_ids:
        if eid not in to_remove:
            result.append(eid)

    # Append newly added items in sorted order for determinism
    for eid in sorted(to_add):
        result.append(eid)

    return result


def should_start_marquee(
    clicked_entity_id: str | None,
    clicked_gizmo: bool,
    editor_mode_active: bool,
) -> bool:
    """Determine if a marquee selection should start.

    Args:
        clicked_entity_id: Entity ID clicked on, or None if empty space.
        clicked_gizmo: Whether a gizmo/handle was clicked.
        editor_mode_active: Whether editor mode is active.

    Returns:
        True if marquee should start.
    """
    if not editor_mode_active:
        return False
    if clicked_entity_id is not None:
        return False
    if clicked_gizmo:
        return False
    return True


def get_marquee_rect_from_state(state: MarqueeState) -> RectF | None:
    """Get the marquee rectangle from state if active.

    Args:
        state: Current marquee state.

    Returns:
        RectF if marquee is active, None otherwise.
    """
    if not state.active:
        return None
    return rect_from_points(state.start_world, state.end_world)
