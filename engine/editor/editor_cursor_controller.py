"""Controller for editor cursor state, hints, and gizmo feedback.

This module extracts cursor hint computation and gizmo feedback state from
EditorModeController for the Vertical Slice Diet V2.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Tuple

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController
    from engine.editor.editor_gizmo_feedback import GizmoFeedbackState


class EditorCursorController:
    """Manages cursor state, hints, and gizmo overlay feedback."""

    def __init__(self, editor: "EditorModeController") -> None:
        self._editor = editor
        self._last_mouse_x: float = 0.0
        self._last_mouse_y: float = 0.0

    def update_mouse_pos(self, x: float, y: float) -> None:
        """Update the last known mouse position.

        Args:
            x: Mouse X in screen coordinates.
            y: Mouse Y in screen coordinates.
        """
        self._last_mouse_x = float(x)
        self._last_mouse_y = float(y)

    def get_last_mouse_pos(self) -> Tuple[float, float]:
        """Get the last known mouse position.

        Returns:
            Tuple of (x, y) in screen coordinates.
        """
        return (self._last_mouse_x, self._last_mouse_y)

    def get_cursor_hint_text(self, window_w: int, window_h: int) -> str | None:
        """Get cursor hint text based on current editor state.

        Args:
            window_w: Window width.
            window_h: Window height.

        Returns:
            Hint text string or None if no hint.
        """
        result = self._compute_cursor_hint(window_w, window_h)
        return result.text if result is not None else None

    def get_cursor_hint_kind(self, window_w: int, window_h: int) -> str | None:
        """Get cursor hint kind for cursor affordance.

        Args:
            window_w: Window width.
            window_h: Window height.

        Returns:
            Cursor kind string or None when editor is inactive.
        """
        result = self._compute_cursor_hint(window_w, window_h)
        return result.kind if result is not None else None

    def _compute_cursor_hint(self, window_w: int, window_h: int):
        """Compute cursor hint based on current editor state."""
        editor = self._editor
        if not editor.active:
            return None

        from engine.editor.editor_cursor_model import build_cursor_hint  # noqa: PLC0415
        from engine.editor_tooltips_model import (  # noqa: PLC0415
            _is_modal_open_state,
            _is_text_input_active_state,
        )

        mouse_x, mouse_y = self._last_mouse_x, self._last_mouse_y

        ui_blocked = _is_text_input_active_state(editor) or _is_modal_open_state(editor)

        from engine.editor.editor_hover_query import (  # noqa: PLC0415
            get_hovered_entity_id,
            get_hovered_splitter,
            get_hovered_top_bar_control_id,
        )
        from engine.editor.editor_menu_hover_query import (  # noqa: PLC0415
            get_menu_hover_item_id,
            get_menu_hover_title,
        )

        splitter_hit = editor.dock.get_drag_active() or get_hovered_splitter(editor)
        entity_hit = get_hovered_entity_id(editor) is not None

        ui_hover = False
        if get_menu_hover_title(editor) is not None:
            ui_hover = True
        if getattr(editor, "_menu_active", None) and get_menu_hover_item_id(editor) is not None:
            ui_hover = True
        dock_ctl = getattr(editor, "dock", None)
        dock_hover = None
        if dock_ctl is not None:
            getter = getattr(dock_ctl, "get_hover_tab", None)
            if callable(getter):
                dock_hover = getter()
        if dock_hover is not None:
            ui_hover = True
        if get_hovered_top_bar_control_id(editor) is not None:
            ui_hover = True

        # Determine gizmo drag state
        move_drag = getattr(editor, "entity_dragging", False) and editor.selected_entity is not None
        rotate_drag = getattr(editor, "_rotate_drag_active", False)
        scale_drag = getattr(editor, "_scale_drag_active", False)
        gizmo_drag_active = move_drag or rotate_drag or scale_drag

        gizmo_mode: str | None = None
        if rotate_drag:
            gizmo_mode = "rotate"
        elif scale_drag:
            gizmo_mode = "scale"
        elif move_drag:
            gizmo_mode = "move"

        return build_cursor_hint(
            editor_active=editor.active,
            mouse_x=mouse_x,
            mouse_y=mouse_y,
            window_w=window_w,
            window_h=window_h,
            ui_blocked=ui_blocked,
            marquee_active=getattr(editor, "_marquee_active", False),
            alt_dup_active=getattr(editor, "_alt_dup_active", False),
            gizmo_drag_active=gizmo_drag_active,
            gizmo_mode=gizmo_mode,
            ui_hover=ui_hover,
            shell_layout=None,
            splitter_hit=splitter_hit,
            entity_hit=entity_hit,
        )

    def get_gizmo_feedback_state(self) -> "GizmoFeedbackState":
        """Get current state for gizmo overlay rendering.

        Returns:
            GizmoFeedbackState snapshot for overlay to render.
        """
        from engine.editor.editor_gizmo_feedback import GizmoFeedbackState  # noqa: PLC0415

        editor = self._editor

        # Determine if any transform drag is active
        move_drag = getattr(editor, "entity_dragging", False) and editor.selected_entity is not None
        rotate_drag = getattr(editor, "_rotate_drag_active", False)
        scale_drag = getattr(editor, "_scale_drag_active", False)
        active = move_drag or rotate_drag or scale_drag

        if not active:
            return GizmoFeedbackState(
                active=False,
                mode="move",
                pivot_xy=None,
                move_delta_xy=None,
                rotate_delta_deg=None,
                scale_factor=None,
                snap_active=False,
            )

        # Determine mode
        if rotate_drag:
            mode = "rotate"
        elif scale_drag:
            mode = "scale"
        else:
            mode = "move"

        # Get pivot position
        pivot_xy = getattr(editor, "_transform_drag_pivot", None)
        if pivot_xy is None and move_drag:
            # For move, use primary entity start position as pivot
            drag_starts = getattr(editor, "_multiselect_drag_starts", {})
            primary_id = getattr(editor, "_primary_entity_id", None)
            if primary_id and primary_id in drag_starts:
                pivot_xy = drag_starts[primary_id]
            elif editor.selected_entity:
                start_pos = getattr(editor, "entity_drag_start_pos", None)
                if start_pos:
                    pivot_xy = start_pos

        return GizmoFeedbackState(
            active=True,
            mode=mode,
            pivot_xy=pivot_xy,
            move_delta_xy=getattr(editor, "_move_preview_delta_xy", None),
            rotate_delta_deg=getattr(editor, "_rotate_preview_delta_deg", None),
            scale_factor=getattr(editor, "_scale_preview_factor", None),
            snap_active=getattr(editor, "_transform_snap_active", False),
        )
