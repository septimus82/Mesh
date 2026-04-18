"""Pure module for selection outline computation.

This module provides deterministic, headless-safe functions for computing
entity selection outlines and group bounds. No arcade dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple


@dataclass(frozen=True, slots=True)
class RectF:
    """Floating-point rectangle with top-left origin.

    Attributes:
        x: Left edge x-coordinate.
        y: Bottom edge y-coordinate (screen/world y).
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

    @property
    def center_x(self) -> float:
        """Center x-coordinate."""
        return self.x + self.w / 2.0

    @property
    def center_y(self) -> float:
        """Center y-coordinate."""
        return self.y + self.h / 2.0

    def contains_point(self, px: float, py: float) -> bool:
        """Check if point is inside rectangle.

        Args:
            px: Point x-coordinate.
            py: Point y-coordinate.

        Returns:
            True if point is inside or on edge.
        """
        return self.left <= px <= self.right and self.bottom <= py <= self.top


@dataclass(frozen=True, slots=True)
class SelectionOutline:
    """Outline data for a selected entity.

    Attributes:
        entity_id: Entity identifier.
        rect: Bounding rectangle in world coordinates.
        is_primary: True if this is the primary selection.
    """

    entity_id: str
    rect: RectF
    is_primary: bool


@dataclass(frozen=True, slots=True)
class GroupBounds:
    """Bounding rectangle for a group of selected entities.

    Attributes:
        rect: AABB union of all selected entity bounds.
    """

    rect: RectF


def resolve_entity_bounds(entity_data: dict, sprite: Any | None) -> RectF | None:
    """Resolve entity bounding rectangle from sprite or entity data.

    Args:
        entity_data: Entity JSON data dict with x, y, and optional width/height.
        sprite: Runtime sprite object (may have center_x, center_y, width, height).

    Returns:
        RectF if bounds can be determined, None otherwise.
    """
    # Try sprite first (runtime data is most accurate)
    if sprite is not None:
        cx = getattr(sprite, "center_x", None)
        cy = getattr(sprite, "center_y", None)
        w = getattr(sprite, "width", None)
        h = getattr(sprite, "height", None)

        if cx is not None and cy is not None and w is not None and h is not None:
            try:
                cx_f = float(cx)
                cy_f = float(cy)
                w_f = float(w)
                h_f = float(h)
                if w_f > 0 and h_f > 0:
                    return RectF(x=cx_f - w_f / 2.0, y=cy_f - h_f / 2.0, w=w_f, h=h_f)
            except (ValueError, TypeError):
                pass

    # Fall back to entity_data
    if not isinstance(entity_data, dict):
        return None

    x = entity_data.get("x")
    y = entity_data.get("y")

    if x is None or y is None:
        return None

    try:
        x_f = float(x)
        y_f = float(y)
    except (ValueError, TypeError):
        return None

    # Try width/height from entity_data
    w = entity_data.get("width") or entity_data.get("w")
    h = entity_data.get("height") or entity_data.get("h")

    if w is not None and h is not None:
        try:
            w_f = float(w)
            h_f = float(h)
            if w_f > 0 and h_f > 0:
                # Entity data x,y is typically center
                return RectF(x=x_f - w_f / 2.0, y=y_f - h_f / 2.0, w=w_f, h=h_f)
        except (ValueError, TypeError):
            pass

    # Default fallback: small rectangle around entity position
    default_size = 32.0
    return RectF(x=x_f - default_size / 2.0, y=y_f - default_size / 2.0, w=default_size, h=default_size)


def build_selection_outlines(
    selected_ids: list[str],
    primary_id: str | None,
    entity_by_id: dict[str, dict],
    sprite_by_id: dict[str, Any],
) -> list[SelectionOutline]:
    """Build selection outlines for selected entities.

    Args:
        selected_ids: List of selected entity IDs (determines order).
        primary_id: ID of the primary selected entity (may be None).
        entity_by_id: Mapping of entity ID to entity JSON data.
        sprite_by_id: Mapping of entity ID to runtime sprite.

    Returns:
        List of SelectionOutline in deterministic order (same as selected_ids).
    """
    outlines: list[SelectionOutline] = []

    for eid in selected_ids:
        entity_data = entity_by_id.get(eid, {})
        sprite = sprite_by_id.get(eid)
        rect = resolve_entity_bounds(entity_data, sprite)

        if rect is None:
            continue

        is_primary = (eid == primary_id)
        outlines.append(SelectionOutline(entity_id=eid, rect=rect, is_primary=is_primary))

    return outlines


def compute_group_bounds(outlines: list[SelectionOutline]) -> GroupBounds | None:
    """Compute AABB union of multiple selection outlines.

    Args:
        outlines: List of selection outlines.

    Returns:
        GroupBounds if 2+ outlines exist, None otherwise.
    """
    if len(outlines) < 2:
        return None

    # Compute AABB union
    min_x = min(o.rect.left for o in outlines)
    min_y = min(o.rect.bottom for o in outlines)
    max_x = max(o.rect.right for o in outlines)
    max_y = max(o.rect.top for o in outlines)

    return GroupBounds(rect=RectF(x=min_x, y=min_y, w=max_x - min_x, h=max_y - min_y))


def rect_to_border_segments(
    rect: RectF,
) -> Tuple[
    Tuple[float, float, float, float],
    Tuple[float, float, float, float],
    Tuple[float, float, float, float],
    Tuple[float, float, float, float],
]:
    """Convert rectangle to four border line segments.

    Args:
        rect: Rectangle to convert.

    Returns:
        Tuple of 4 segments (top, right, bottom, left).
        Each segment is (x1, y1, x2, y2).
    """
    left, right, bottom, top = rect.left, rect.right, rect.bottom, rect.top

    # Order: top, right, bottom, left
    top_seg = (left, top, right, top)
    right_seg = (right, top, right, bottom)
    bottom_seg = (right, bottom, left, bottom)
    left_seg = (left, bottom, left, top)

    return (top_seg, right_seg, bottom_seg, left_seg)


def rect_to_corner_markers(
    rect: RectF,
    marker_size: float = 8.0,
) -> list[Tuple[Tuple[float, float, float, float], Tuple[float, float, float, float]]]:
    """Generate corner marker segments for primary selection emphasis.

    Args:
        rect: Rectangle for corners.
        marker_size: Length of corner tick marks.

    Returns:
        List of 4 corner markers, each as (horizontal_seg, vertical_seg).
    """
    left, right, bottom, top = rect.left, rect.right, rect.bottom, rect.top
    s = marker_size

    corners = [
        # Top-left: horizontal goes right, vertical goes down
        ((left, top, left + s, top), (left, top, left, top - s)),
        # Top-right: horizontal goes left, vertical goes down
        ((right - s, top, right, top), (right, top, right, top - s)),
        # Bottom-right: horizontal goes left, vertical goes up
        ((right - s, bottom, right, bottom), (right, bottom, right, bottom + s)),
        # Bottom-left: horizontal goes right, vertical goes up
        ((left, bottom, left + s, bottom), (left, bottom, left, bottom + s)),
    ]

    return corners


# -----------------------------------------------------------------------------
# Selection Style Resolution (for Alt-Drag Duplicate highlighting)
# -----------------------------------------------------------------------------

# Style constants
STYLE_NORMAL = "normal"
STYLE_ORIGINAL = "original"
STYLE_DUPLICATE = "duplicate"
STYLE_HOVER = "hover"  # For hovered (non-selected) entities


def resolve_selection_styles(
    selected_ids: list[str],
    alt_dup_active: bool,
    alt_dup_original_ids: list[str] | None,
    alt_dup_duplicate_ids: list[str] | None,
) -> dict[str, str]:
    """Resolve visual style for each selected entity.

    During alt-drag duplicate:
      - Original entities get "original" style (ghosted/dim)
      - Duplicated entities get "duplicate" style (highlighted)
    Otherwise all selected get "normal" style.

    Args:
        selected_ids: List of currently selected entity IDs.
        alt_dup_active: Whether alt-drag duplicate is active.
        alt_dup_original_ids: Original entity IDs being duplicated (if active).
        alt_dup_duplicate_ids: New duplicate entity IDs (if active).

    Returns:
        Dict mapping entity_id -> style ("normal" | "original" | "duplicate").
        Keys are sorted for determinism.
    """
    result: dict[str, str] = {}

    if not alt_dup_active:
        # Normal mode: all selected entities get "normal" style
        for eid in sorted(selected_ids):
            result[eid] = STYLE_NORMAL
        return result

    # Alt-drag duplicate active: categorize entities
    original_set = set(alt_dup_original_ids or [])
    duplicate_set = set(alt_dup_duplicate_ids or [])

    for eid in sorted(selected_ids):
        if eid in duplicate_set:
            result[eid] = STYLE_DUPLICATE
        elif eid in original_set:
            result[eid] = STYLE_ORIGINAL
        else:
            result[eid] = STYLE_NORMAL

    # Also include originals that may not be in current selection
    # (they should still be shown as ghosts)
    for eid in sorted(original_set):
        if eid not in result:
            result[eid] = STYLE_ORIGINAL

    return result


def resolve_primary_for_alt_dup(
    current_primary_id: str | None,
    alt_dup_active: bool,
    alt_dup_pivot_new_id: str | None,
) -> str | None:
    """Resolve which entity should be treated as primary for outline styling.

    During alt-drag duplicate, the primary duplicate (pivot) takes precedence.

    Args:
        current_primary_id: Current primary entity ID from selection.
        alt_dup_active: Whether alt-drag duplicate is active.
        alt_dup_pivot_new_id: The duplicated pivot entity ID (if available).

    Returns:
        Entity ID to treat as primary for outline styling.
    """
    if alt_dup_active and alt_dup_pivot_new_id:
        return alt_dup_pivot_new_id
    return current_primary_id


@dataclass(frozen=True, slots=True)
class StyledSelectionOutline:
    """Outline data for a selected entity with style information.

    Attributes:
        entity_id: Entity identifier.
        rect: Bounding rectangle in world coordinates.
        is_primary: True if this is the primary selection.
        style: Visual style ("normal" | "original" | "duplicate").
    """

    entity_id: str
    rect: RectF
    is_primary: bool
    style: str


def build_selection_outlines_with_styles(
    selected_ids: list[str],
    primary_id: str | None,
    entity_by_id: dict[str, dict],
    sprite_by_id: dict[str, Any],
    style_map: dict[str, str] | None = None,
) -> list[StyledSelectionOutline]:
    """Build selection outlines with style information for selected entities.

    Args:
        selected_ids: List of selected entity IDs (determines order).
        primary_id: ID of the primary selected entity (may be None).
        entity_by_id: Mapping of entity ID to entity JSON data.
        sprite_by_id: Mapping of entity ID to runtime sprite.
        style_map: Optional mapping of entity_id -> style string.
                   If None, all entities get "normal" style.

    Returns:
        List of StyledSelectionOutline in deterministic order.
    """
    outlines: list[StyledSelectionOutline] = []

    # Collect all IDs to process (selected + any extras in style_map)
    all_ids = list(selected_ids)
    if style_map:
        for eid in style_map:
            if eid not in all_ids:
                all_ids.append(eid)

    # Sort for deterministic ordering
    sorted_ids = sorted(all_ids)

    for eid in sorted_ids:
        entity_data = entity_by_id.get(eid, {})
        sprite = sprite_by_id.get(eid)
        rect = resolve_entity_bounds(entity_data, sprite)

        if rect is None:
            continue

        is_primary = (eid == primary_id)
        style = (style_map or {}).get(eid, STYLE_NORMAL)
        outlines.append(StyledSelectionOutline(
            entity_id=eid,
            rect=rect,
            is_primary=is_primary,
            style=style,
        ))

    return outlines

