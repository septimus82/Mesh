from __future__ import annotations

from typing import Any, Dict, List

from ..editor.state import (
    TRANSFORM_MODE_MOVE,
    TRANSFORM_MODE_ROTATE,
    TRANSFORM_MODE_SCALE,
)
from ..logging_tools import get_logger

logger = get_logger(__name__)


def apply_selection(
    controller: Any,
    selected_entity: Any | None,
    shift: bool = False,
    *,
    click_world: tuple[float, float] | None = None,
) -> None:
    """Apply selection change side-effects (mirrors legacy editor_controller behavior).

    Args:
        controller: The editor controller.
        selected_entity: The clicked entity (or None to clear).
        shift: Whether Shift was held (for multi-select toggle).
    """
    from ..editor.editor_multiselect_ops import select_single, toggle_selection  # noqa: PLC0415
    from ..editor.editor_transform_ops import resolve_entity_id_for_sprite  # noqa: PLC0415

    if getattr(controller, "shape_edit_mode", None) and selected_entity is not getattr(
        controller, "shape_edit_entity", None
    ):
        cancel = getattr(getattr(controller, "shape", None), "cancel_shape_edit", None)
        if callable(cancel):
            cancel()

    # Update multi-selection state
    clicked_id = resolve_entity_id_for_sprite(selected_entity) if selected_entity else None
    current_ids: List[str] = getattr(controller, "_selected_entity_ids", [])

    if selected_entity:
        if shift:
            new_ids = toggle_selection(current_ids, clicked_id or "", shift=True)
        else:
            new_ids = select_single(clicked_id or "")
        controller._selected_entity_ids = new_ids

        # Primary is the clicked entity (for drag anchor)
        controller._primary_entity_id = clicked_id

        # Legacy single selection for compatibility
        controller.selected_entity = selected_entity
    else:
        controller._selected_entity_ids = []
        controller._primary_entity_id = None
        controller.selected_entity = None

    if selected_entity:
        cancel_marquee = getattr(controller, "cancel_marquee", None)
        if callable(cancel_marquee):
            cancel_marquee()

        # Plain MOVE-tool clicks select and immediately prepare viewport drag.
        if controller.tool_mode == "MOVE" and clicked_id and not shift:
            transform_mode = getattr(controller, "transform_mode", TRANSFORM_MODE_MOVE)
            if transform_mode == TRANSFORM_MODE_MOVE:
                controller.entity_dragging = True
                if click_world is not None:
                    controller.entity_drag_start_pos = (float(click_world[0]), float(click_world[1]))
                else:
                    controller.entity_drag_start_pos = (
                        controller.selected_entity.center_x,
                        controller.selected_entity.center_y,
                    )
                # Store start positions for all selected entities
                _init_multiselect_drag_starts(controller)
            elif transform_mode == TRANSFORM_MODE_ROTATE:
                _init_rotate_drag(controller)
            elif transform_mode == TRANSFORM_MODE_SCALE:
                _init_scale_drag(controller)

        controller.shape.reset_zone_selection_state()
        controller.shape.sync_zone_selection_state(controller.selected_entity)
        controller._cancel_hierarchy_rename()
        controller._refresh_dialogue_cache()
        controller._refresh_animation_cache()
        controller._refresh_tile_palette()
        name = controller._get_display_name_for_sprite(controller.selected_entity)
        logger.info(
            "[Editor] Selected: %s at (%.1f, %.1f) [%d total]",
            name,
            controller.selected_entity.center_x,
            controller.selected_entity.center_y,
            len(controller._selected_entity_ids),
        )

        # Reset inspector
        inspector = getattr(controller, "inspector", None)
        if inspector is not None:
            inspector.set_inspector_active(False)
        controller.inspector_selection_index = 0
        controller._refresh_inspector_items()
        controller.dialogue_panel_active = False
        controller.dialogue_editing = False
        controller.animation_active = False
        controller.animation_editing = False
        controller.tile_panel_active = False

        # Sync hierarchy selection if open
        if controller.hierarchy_active:
            controller._refresh_hierarchy_list()
            try:
                controller.hierarchy_selection_index = controller._cached_hierarchy_list.index(controller.selected_entity)
            except ValueError:
                pass
    else:
        inspector = getattr(controller, "inspector", None)
        if inspector is not None:
            inspector.set_inspector_active(False)
        controller.shape.reset_zone_selection_state()
        controller._cancel_hierarchy_rename()
        controller._close_dialogue_panel()
        controller._close_animation_panel()
        controller._close_tile_panel()


def _init_multiselect_drag_starts(controller: Any) -> None:
    """Initialize drag start positions for all selected entities.

    Stores current positions keyed by entity ID for computing deltas during drag.
    """
    from ..editor.editor_transform_ops import resolve_entity_id_for_sprite  # noqa: PLC0415
    from .editor_input_click_handlers import _iter_entity_sprite_sources  # noqa: PLC0415

    drag_starts: Dict[str, tuple[float, float]] = {}
    selected_ids: List[str] = getattr(controller, "_selected_entity_ids", [])

    if not selected_ids:
        controller._multiselect_drag_starts = drag_starts
        return

    sc = getattr(controller.window, "scene_controller", None)
    if sc is None:
        controller._multiselect_drag_starts = drag_starts
        return

    seen: set[int] = set()
    for source in _iter_entity_sprite_sources(sc):
        for sprite in list(source or []):
            marker = id(sprite)
            if marker in seen:
                continue
            seen.add(marker)
            eid = resolve_entity_id_for_sprite(sprite)
            if eid and eid in selected_ids:
                drag_starts[eid] = (sprite.center_x, sprite.center_y)

    controller._multiselect_drag_starts = drag_starts


def get_sprite_for_entity_id(controller: Any, entity_id: str) -> Any | None:
    """Find sprite by entity ID.

    Args:
        controller: The editor controller.
        entity_id: Entity ID to find.

    Returns:
        Sprite if found, None otherwise.
    """
    from ..editor.editor_transform_ops import resolve_entity_id_for_sprite  # noqa: PLC0415
    from .editor_input_click_handlers import _iter_entity_sprite_sources  # noqa: PLC0415

    sc = getattr(controller.window, "scene_controller", None)
    if sc is None:
        return None

    seen: set[int] = set()
    for source in _iter_entity_sprite_sources(sc):
        for sprite in list(source or []):
            marker = id(sprite)
            if marker in seen:
                continue
            seen.add(marker)
            eid = resolve_entity_id_for_sprite(sprite)
            if eid == entity_id:
                return sprite
    return None


def _init_rotate_drag(controller: Any) -> None:
    """Initialize rotation drag state for multi-select.

    Sets up pivot (primary entity position), mouse start position,
    and start rotations for all selected entities.
    """

    selected_ids: List[str] = getattr(controller, "_selected_entity_ids", [])
    primary_id = getattr(controller, "_primary_entity_id", None)

    if not selected_ids:
        return

    # Get primary entity position as pivot
    primary_sprite = get_sprite_for_entity_id(controller, primary_id) if primary_id else None
    if primary_sprite is None:
        return

    pivot = (primary_sprite.center_x, primary_sprite.center_y)

    # Store start rotations for all selected entities
    start_rots: Dict[str, float] = {}
    for eid in selected_ids:
        sprite = get_sprite_for_entity_id(controller, eid)
        if sprite:
            start_rots[eid] = getattr(sprite, "angle", 0.0)

    # Get current mouse position in world coords
    # Note: We'll update this on first drag move, use pivot as initial
    mouse_start = pivot

    controller._rotate_drag_active = True
    controller._transform_drag_pivot = pivot
    controller._transform_drag_mouse_start = mouse_start
    controller._transform_drag_start_rots = start_rots

    logger.info("[Editor] Started rotate drag with pivot at (%.1f, %.1f)", pivot[0], pivot[1])


def _init_scale_drag(controller: Any) -> None:
    """Initialize scale drag state for multi-select.

    Sets up pivot (primary entity position), mouse start position,
    and start scales for all selected entities.
    """

    selected_ids: List[str] = getattr(controller, "_selected_entity_ids", [])
    primary_id = getattr(controller, "_primary_entity_id", None)

    if not selected_ids:
        return

    # Get primary entity position as pivot
    primary_sprite = get_sprite_for_entity_id(controller, primary_id) if primary_id else None
    if primary_sprite is None:
        return

    pivot = (primary_sprite.center_x, primary_sprite.center_y)

    # Store start scales for all selected entities
    start_scales: Dict[str, float] = {}
    for eid in selected_ids:
        sprite = get_sprite_for_entity_id(controller, eid)
        if sprite:
            scale = getattr(sprite, "scale", 1.0)
            # Handle tuple/scalar scale - use uniform scale
            if isinstance(scale, tuple):
                scale = scale[0] if scale else 1.0
            start_scales[eid] = float(scale)

    # Get current mouse position in world coords
    # Note: We'll update this on first drag move, use pivot as initial
    mouse_start = pivot

    controller._scale_drag_active = True
    controller._transform_drag_pivot = pivot
    controller._transform_drag_mouse_start = mouse_start
    controller._transform_drag_start_scales = start_scales

    logger.info("[Editor] Started scale drag with pivot at (%.1f, %.1f)", pivot[0], pivot[1])
