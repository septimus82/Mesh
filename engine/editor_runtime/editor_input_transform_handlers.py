from __future__ import annotations

from typing import TYPE_CHECKING

import engine.optional_arcade as optional_arcade

from ..logging_tools import get_logger

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController as EditorController

logger = get_logger(__name__)


def handle_rotate_drag(controller: EditorController, wx: float, wy: float, modifiers: int) -> bool:
    """Handle mouse drag during rotation transform."""
    from ..editor.editor_rotate_ops import (  # noqa: PLC0415
        compute_angle_deg,
        snap_rot_deg,
    )
    from .state import get_sprite_for_entity_id  # noqa: PLC0415

    pivot = getattr(controller, "_transform_drag_pivot", None)
    mouse_start = getattr(controller, "_transform_drag_mouse_start", None)
    start_rots = getattr(controller, "_transform_drag_start_rots", {})
    selected_ids = getattr(controller, "_selected_entity_ids", [])

    if pivot is None or not start_rots:
        return False

    # Capture first drag position as mouse_start if not set
    if mouse_start is None or mouse_start == pivot:
        controller._transform_drag_mouse_start = (wx, wy)
        return True  # First frame, don't apply yet

    # Compute rotation delta from pivot
    start_angle = compute_angle_deg(pivot[0], pivot[1], mouse_start[0], mouse_start[1])
    current_angle = compute_angle_deg(pivot[0], pivot[1], wx, wy)
    delta = current_angle - start_angle
    # Wrap to [-180, 180]
    while delta > 180.0:
        delta -= 360.0
    while delta < -180.0:
        delta += 360.0

    # Apply snapping if enabled (Shift = 15 degree increments)
    snap_enabled = bool(modifiers & optional_arcade.arcade.key.MOD_SHIFT)
    if snap_enabled:
        delta = snap_rot_deg(delta, 15.0)

    # Store preview state for gizmo overlay
    controller._rotate_preview_delta_deg = delta
    controller._transform_snap_active = snap_enabled

    # Apply rotation to all selected entities
    for eid in selected_ids:
        sprite = get_sprite_for_entity_id(controller, eid)
        if sprite and eid in start_rots:
            sprite.angle = start_rots[eid] + delta

    return True


def handle_scale_drag(controller: EditorController, wx: float, wy: float, modifiers: int) -> bool:
    """Handle mouse drag during scale transform."""
    from ..editor.editor_scale_ops import (  # noqa: PLC0415
        clamp_scale,
        compute_scale_factor,
        snap_scale_factor,
    )
    from .state import get_sprite_for_entity_id  # noqa: PLC0415

    pivot = getattr(controller, "_transform_drag_pivot", None)
    mouse_start = getattr(controller, "_transform_drag_mouse_start", None)
    start_scales = getattr(controller, "_transform_drag_start_scales", {})
    selected_ids = getattr(controller, "_selected_entity_ids", [])

    if pivot is None or not start_scales:
        return False

    # Capture first drag position as mouse_start if not set
    if mouse_start is None or mouse_start == pivot:
        controller._transform_drag_mouse_start = (wx, wy)
        return True  # First frame, don't apply yet

    # Compute scale factor from pivot distance
    factor = compute_scale_factor(pivot, mouse_start, (wx, wy))

    # Apply snapping if enabled (Shift = 0.1 increments)
    snap_enabled = modifiers & optional_arcade.arcade.key.MOD_SHIFT
    if snap_enabled:
        factor = snap_scale_factor(factor, 0.1)

    # Store preview state for gizmo overlay
    controller._scale_preview_factor = factor
    controller._transform_snap_active = bool(snap_enabled)

    # Apply scale to all selected entities
    for eid in selected_ids:
        sprite = get_sprite_for_entity_id(controller, eid)
        if sprite and eid in start_scales:
            new_scale = clamp_scale(start_scales[eid] * factor)
            sprite.scale = new_scale

    return True


def finish_rotate_drag(controller: EditorController) -> bool:
    """Finish rotation drag and push command to undo stack."""
    from ..editor.editor_rotate_ops import (  # noqa: PLC0415
        RotateEntityCommand,
        RotateEntitiesCommand,
    )
    from .state import get_sprite_for_entity_id  # noqa: PLC0415

    start_rots = getattr(controller, "_transform_drag_start_rots", {})
    selected_ids = getattr(controller, "_selected_entity_ids", [])

    rotates = []
    any_changed = False
    for eid in selected_ids:
        start_rot = start_rots.get(eid)
        if start_rot is None:
            continue
        sprite = get_sprite_for_entity_id(controller, eid)
        if sprite:
            end_rot = getattr(sprite, "angle", 0.0)
            if abs(end_rot - start_rot) > 0.001:
                any_changed = True
            rotates.append(RotateEntityCommand(entity_id=eid, start_rot_deg=start_rot, end_rot_deg=end_rot))

    if any_changed and rotates:
        group_cmd = RotateEntitiesCommand(rotates=tuple(rotates))
        controller._push_command(group_cmd.to_dict())
        logger.info("[Editor] Rotated %d entities", len(rotates))

    # Reset drag state
    controller._rotate_drag_active = False
    controller._transform_drag_pivot = None
    controller._transform_drag_mouse_start = None
    controller._transform_drag_start_rots = {}
    # Clear preview state for gizmo overlay
    controller._rotate_preview_delta_deg = None
    controller._transform_snap_active = False

    return True


def finish_scale_drag(controller: EditorController) -> bool:
    """Finish scale drag and push command to undo stack."""
    from ..editor.editor_scale_ops import (  # noqa: PLC0415
        ScaleEntityCommand,
        ScaleEntitiesCommand,
    )
    from .state import get_sprite_for_entity_id  # noqa: PLC0415

    start_scales = getattr(controller, "_transform_drag_start_scales", {})
    selected_ids = getattr(controller, "_selected_entity_ids", [])

    scales = []
    any_changed = False
    for eid in selected_ids:
        start_scale = start_scales.get(eid)
        if start_scale is None:
            continue
        sprite = get_sprite_for_entity_id(controller, eid)
        if sprite:
            end_scale = getattr(sprite, "scale", 1.0)
            if isinstance(end_scale, tuple):
                end_scale = end_scale[0] if end_scale else 1.0
            if abs(end_scale - start_scale) > 0.001:
                any_changed = True
            scales.append(ScaleEntityCommand(entity_id=eid, start_scale=start_scale, end_scale=float(end_scale)))

    if any_changed and scales:
        group_cmd = ScaleEntitiesCommand(scales=tuple(scales))
        controller._push_command(group_cmd.to_dict())
        logger.info("[Editor] Scaled %d entities", len(scales))

    # Reset drag state
    controller._scale_drag_active = False
    controller._transform_drag_pivot = None
    controller._transform_drag_mouse_start = None
    controller._transform_drag_start_scales = {}
    # Clear preview state for gizmo overlay
    controller._scale_preview_factor = None
    controller._transform_snap_active = False

    return True
