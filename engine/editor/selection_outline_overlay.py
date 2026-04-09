"""Editor overlay for selection outlines.

Renders entity selection outlines and group bounds in world space.
Supports distinct styles during alt-drag duplicate:
  - "original" = ghosted (dim + thin)
  - "duplicate" = highlighted (bright + thicker)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import engine.optional_arcade as optional_arcade
from ..logging_tools import get_logger
from ..ui_overlays.common import UIElement
from .selection_outline import (
    RectF,
    SelectionOutline,
    StyledSelectionOutline,
    GroupBounds,
    build_selection_outlines,
    build_selection_outlines_with_styles,
    compute_group_bounds,
    rect_to_border_segments,
    rect_to_corner_markers,
    resolve_selection_styles,
    resolve_primary_for_alt_dup,
    STYLE_NORMAL,
    STYLE_ORIGINAL,
    STYLE_DUPLICATE,
    STYLE_HOVER,
)
from .editor_hover_query import get_hovered_entity_id, get_hovered_entity_rect

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController

logger = get_logger(__name__)

# Colors (RGBA)
OUTLINE_COLOR = (100, 200, 255, 200)  # Cyan-ish
PRIMARY_OUTLINE_COLOR = (255, 255, 100, 255)  # Bright yellow
GROUP_BOUNDS_COLOR = (150, 150, 200, 120)  # Softer blue-gray

# Alt-drag duplicate style colors
ORIGINAL_GHOST_COLOR = (100, 200, 255, 80)  # Dim cyan (ghosted originals)
DUPLICATE_HIGHLIGHT_COLOR = (120, 255, 180, 255)  # Bright green-cyan (duplicates)
DUPLICATE_PRIMARY_COLOR = (255, 255, 100, 255)  # Bright yellow (primary duplicate)

# Hover style color (warm orange, subtle)
HOVER_OUTLINE_COLOR = (255, 200, 100, 150)  # Warm orange for hover

# Line widths
OUTLINE_LINE_WIDTH = 1.5
PRIMARY_LINE_WIDTH = 2.0
GROUP_LINE_WIDTH = 1.0
PRIMARY_CORNER_SIZE = 10.0

# Alt-drag duplicate line widths
ORIGINAL_LINE_WIDTH = 1.0  # Thinner for ghosts
DUPLICATE_LINE_WIDTH = 2.0  # Thicker for duplicates

# Hover line width
HOVER_LINE_WIDTH = 1.0  # Thin for hover


class SelectionOutlineOverlay(UIElement):
    """Overlay for rendering selection outlines in world space."""

    def __init__(self, window: Any) -> None:
        """Initialize overlay.

        Args:
            window: Game window to query controller from.
        """
        super().__init__(window)
        self._visible = True

    @property
    def controller(self) -> "EditorModeController | None":
        """Get editor controller from window."""
        return getattr(self.window, "editor_controller", None)

    def update(self, dt: float) -> None:  # noqa: ARG002
        """Update overlay (no-op for this overlay)."""
        pass

    def draw(self) -> None:
        """Draw overlay (delegates to draw_world for outlines)."""
        # Outlines are drawn in world space by draw_world, called separately
        pass

    def draw_world(self) -> None:
        """Draw world-space selection outlines.

        Should be called within the world camera context.
        During alt-drag duplicate, shows distinct styles:
          - Original entities = ghosted (dim + thin)
          - Duplicated entities = highlighted (bright + thicker)
        """
        controller = self.controller
        if controller is None or not getattr(controller, "active", False):
            return

        if not self._visible:
            return

        # Check alt-drag duplicate state
        alt_dup_active = getattr(controller, "_alt_dup_active", False)
        alt_dup_original_ids = getattr(controller, "_alt_dup_original_selection", None)
        alt_dup_specs = getattr(controller, "_alt_dup_specs", None)
        alt_dup_pivot_new_id = getattr(controller, "_alt_dup_pivot_new_id", None)

        # Get duplicate IDs from specs
        alt_dup_duplicate_ids: list[str] = []
        if alt_dup_specs:
            alt_dup_duplicate_ids = [spec.new_id for spec in alt_dup_specs]

        # Gather selection state
        selected_ids = self._get_selected_entity_ids(controller)

        # During alt-dup, also include original IDs for ghosting
        all_ids_to_render = list(selected_ids)
        if alt_dup_active and alt_dup_original_ids:
            for oid in alt_dup_original_ids:
                if oid not in all_ids_to_render:
                    all_ids_to_render.append(oid)

        if not all_ids_to_render:
            return

        # Resolve styles and primary
        style_map = resolve_selection_styles(
            selected_ids=all_ids_to_render,
            alt_dup_active=alt_dup_active,
            alt_dup_original_ids=alt_dup_original_ids,
            alt_dup_duplicate_ids=alt_dup_duplicate_ids,
        )

        # Resolve primary: during alt-dup, prefer the pivot duplicate
        current_primary = self._get_primary_entity_id(controller)
        effective_primary = resolve_primary_for_alt_dup(
            current_primary_id=current_primary,
            alt_dup_active=alt_dup_active,
            alt_dup_pivot_new_id=alt_dup_pivot_new_id,
        )

        entity_by_id = self._build_entity_lookup(controller)
        sprite_by_id = self._build_sprite_lookup(controller, all_ids_to_render)

        # Build styled outlines
        outlines = build_selection_outlines_with_styles(
            selected_ids=all_ids_to_render,
            primary_id=effective_primary,
            entity_by_id=entity_by_id,
            sprite_by_id=sprite_by_id,
            style_map=style_map,
        )

        if not outlines:
            return

        # Compute group bounds (only for duplicates during alt-dup, or all otherwise)
        if alt_dup_active:
            # Group bounds only for duplicates
            duplicate_outlines = [o for o in outlines if o.style == STYLE_DUPLICATE]
            group_bounds = self._compute_group_bounds_from_styled(duplicate_outlines)
        else:
            # Normal: group bounds for all
            group_bounds = self._compute_group_bounds_from_styled(outlines)

        arcade = optional_arcade.arcade

        # Draw order: group bounds, then originals (ghosts), then duplicates/normal, then primary

        # 1. Draw group bounds
        if group_bounds is not None:
            self._draw_rect_outline(arcade, group_bounds.rect, GROUP_BOUNDS_COLOR, GROUP_LINE_WIDTH)

        # 2. Draw original (ghosted) outlines first (they're behind)
        for outline in outlines:
            if outline.style == STYLE_ORIGINAL:
                self._draw_rect_outline(arcade, outline.rect, ORIGINAL_GHOST_COLOR, ORIGINAL_LINE_WIDTH)

        # 3. Draw normal outlines (non-primary)
        for outline in outlines:
            if outline.style == STYLE_NORMAL and not outline.is_primary:
                self._draw_rect_outline(arcade, outline.rect, OUTLINE_COLOR, OUTLINE_LINE_WIDTH)

        # 4. Draw duplicate outlines (non-primary)
        for outline in outlines:
            if outline.style == STYLE_DUPLICATE and not outline.is_primary:
                self._draw_rect_outline(arcade, outline.rect, DUPLICATE_HIGHLIGHT_COLOR, DUPLICATE_LINE_WIDTH)

        # 5. Draw primary outline with emphasis
        for outline in outlines:
            if outline.is_primary:
                if outline.style == STYLE_DUPLICATE:
                    # Primary duplicate: bright yellow
                    self._draw_rect_outline(arcade, outline.rect, DUPLICATE_PRIMARY_COLOR, PRIMARY_LINE_WIDTH)
                    self._draw_corner_markers(arcade, outline.rect, DUPLICATE_PRIMARY_COLOR, PRIMARY_LINE_WIDTH)
                elif outline.style == STYLE_NORMAL:
                    # Normal primary
                    self._draw_rect_outline(arcade, outline.rect, PRIMARY_OUTLINE_COLOR, PRIMARY_LINE_WIDTH)
                    self._draw_corner_markers(arcade, outline.rect, PRIMARY_OUTLINE_COLOR, PRIMARY_LINE_WIDTH)
                # Note: original style entities shouldn't be primary during alt-dup

        # 6. Draw hover outline for non-selected entity (if any)
        self._draw_hover_outline(arcade, controller, all_ids_to_render)

    def _draw_hover_outline(self, arcade: Any, controller: Any, selected_ids: list[str]) -> None:
        """Draw outline for hovered (non-selected) entity.

        Args:
            arcade: Arcade module reference.
            controller: Editor controller.
            selected_ids: List of currently selected entity IDs.
        """
        hover_entity_id = get_hovered_entity_id(controller)
        if not hover_entity_id:
            return

        # Don't draw hover outline for selected entities
        if hover_entity_id in selected_ids:
            return

        hover_entity_rect = get_hovered_entity_rect(controller)
        if not hover_entity_rect:
            return

        # Convert tuple to RectF
        rect = RectF(
            x=hover_entity_rect[0],
            y=hover_entity_rect[1],
            w=hover_entity_rect[2],
            h=hover_entity_rect[3],
        )

        self._draw_rect_outline(arcade, rect, HOVER_OUTLINE_COLOR, HOVER_LINE_WIDTH)

    def _compute_group_bounds_from_styled(
        self,
        outlines: list[StyledSelectionOutline],
    ) -> GroupBounds | None:
        """Compute group bounds from styled outlines.

        Args:
            outlines: List of styled selection outlines.

        Returns:
            GroupBounds if 2+ outlines exist, None otherwise.
        """
        if len(outlines) < 2:
            return None

        min_x = min(o.rect.left for o in outlines)
        min_y = min(o.rect.bottom for o in outlines)
        max_x = max(o.rect.right for o in outlines)
        max_y = max(o.rect.top for o in outlines)

        return GroupBounds(rect=RectF(x=min_x, y=min_y, w=max_x - min_x, h=max_y - min_y))

    def draw_ui(self) -> None:
        """Draw UI elements (optional label)."""
        # Skipping "Selected: N" label for v1 simplicity
        pass

    def _draw_rect_outline(
        self,
        arcade: Any,
        rect: RectF,
        color: tuple,
        line_width: float,
    ) -> None:
        """Draw rectangle outline using line segments.

        Args:
            arcade: Arcade module reference.
            rect: Rectangle to draw.
            color: Line color (RGBA tuple).
            line_width: Line thickness in pixels.
        """
        segments = rect_to_border_segments(rect)
        draw_line = getattr(arcade, "draw_line", None)

        if draw_line is not None:
            try:
                for seg in segments:
                    draw_line(seg[0], seg[1], seg[2], seg[3], color, line_width)
            except (AttributeError, TypeError):
                # Fallback if draw_line doesn't work as expected
                pass

    def _draw_corner_markers(
        self,
        arcade: Any,
        rect: RectF,
        color: tuple,
        line_width: float,
    ) -> None:
        """Draw corner tick markers for primary selection emphasis.

        Args:
            arcade: Arcade module reference.
            rect: Rectangle for corners.
            color: Line color (RGBA tuple).
            line_width: Line thickness in pixels.
        """
        corners = rect_to_corner_markers(rect, PRIMARY_CORNER_SIZE)
        draw_line = getattr(arcade, "draw_line", None)

        if draw_line is not None:
            try:
                for h_seg, v_seg in corners:
                    draw_line(h_seg[0], h_seg[1], h_seg[2], h_seg[3], color, line_width + 1.0)
                    draw_line(v_seg[0], v_seg[1], v_seg[2], v_seg[3], color, line_width + 1.0)
            except (AttributeError, TypeError):
                pass

    def _get_selected_entity_ids(self, controller: Any) -> list[str]:
        """Get selected entity IDs from controller.

        Args:
            controller: Editor controller.

        Returns:
            List of selected entity IDs.
        """
        return list(getattr(controller, "_selected_entity_ids", []))

    def _get_primary_entity_id(self, controller: Any) -> str | None:
        """Get primary entity ID from controller.

        Args:
            controller: Editor controller.

        Returns:
            Primary entity ID or None.
        """
        return getattr(controller, "_primary_entity_id", None)

    def _build_entity_lookup(self, controller: Any) -> dict[str, dict]:
        """Build entity ID to entity data mapping.

        Args:
            controller: Editor controller.

        Returns:
            Dict mapping entity ID to entity JSON data.
        """
        result: dict[str, dict] = {}

        sc = getattr(self.window, "scene_controller", None)
        if sc is None:
            return result

        scene_data = getattr(sc, "current_scene_data", None)
        if scene_data is None or not isinstance(scene_data, dict):
            return result

        entities = scene_data.get("entities", [])
        if not isinstance(entities, list):
            return result

        for entity in entities:
            if isinstance(entity, dict):
                eid = entity.get("id")
                if eid:
                    result[eid] = entity

        return result

    def _build_sprite_lookup(self, controller: Any, entity_ids: list[str]) -> dict[str, Any]:
        """Build entity ID to sprite mapping for given IDs.

        Args:
            controller: Editor controller.
            entity_ids: List of entity IDs to look up.

        Returns:
            Dict mapping entity ID to sprite (if found).
        """
        result: dict[str, Any] = {}

        from ..editor_runtime.state import get_sprite_for_entity_id  # noqa: PLC0415

        for eid in entity_ids:
            sprite = get_sprite_for_entity_id(controller, eid)
            if sprite is not None:
                result[eid] = sprite

        return result
