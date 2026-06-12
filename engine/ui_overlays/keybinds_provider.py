"""
Overlay provider for Keybinds UI.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

# Visual constants (can be overridden by caller but defaults useful for stateless calculation)
DEFAULT_ROW_HEIGHT = 24
DEFAULT_VIEWPORT_HEIGHT = 400

def get_keybinds_ui_data(
    controller: Any,
    viewport_height: int = DEFAULT_VIEWPORT_HEIGHT,
    row_height: int = DEFAULT_ROW_HEIGHT,
    current_scroll_y: float = 0.0
) -> dict[str, Any]:
    """
    Return data for rendering the keybinds UI.
    
    Performs stateless scroll calculation based on current controller selection.
    """
    from engine.editor.keybinds_window_model import (
        auto_scroll_to_selection,
        clamp_scroll,
        slice_visible_rows,
    )

    state = controller.state
    # Controller properties (like visible_rows) recalculate if dirty
    rows = controller.visible_rows
    total_rows = len(rows)

    # Calculate optimal scroll to keep selection in view
    # Note: We return the *target* scroll. The UI overlay usually consumes this
    # and interpolates or snaps its internal scroll variable.
    target_scroll_y = auto_scroll_to_selection(
        current_scroll_y,
        state.selected_index,
        float(row_height),
        float(viewport_height)
    )

    # Clamp just in case inputs were wild
    target_scroll_y = clamp_scroll(target_scroll_y, total_rows, float(row_height), float(viewport_height))

    # Slice for rendering
    start_idx, end_idx, visible_slice = slice_visible_rows(
        rows, target_scroll_y, float(viewport_height), float(row_height)
    )

    row_data = []
    for i, row in enumerate(visible_slice):
        abs_index = start_idx + i
        row_data.append({
            "index": abs_index,
            "title": row.title,
            "command_id": row.action_id,
            "shortcut": row.shortcut_effective,
            "default": row.shortcut_default,
            "scope": row.scope,
            "has_conflict": bool(row.conflict_ids),
            "conflict_ids": row.conflict_ids,
            "has_override": row.has_override,
            "is_selected": abs_index == state.selected_index,
            "is_recording": (
                state.recording
                and state.recording_target == (row.scope, row.action_id)
            )
        })

    # Check persistence capability
    from engine.editor.editor_actions import _is_web_runtime
    is_web = _is_web_runtime()

    return {
        "visible": state.visible,
        "query": state.query,
        "recording": state.recording,
        "recording_target": state.recording_target, # (scope, id) tuple or None
        "pending_record_shortcut": state.pending_record_shortcut,
        "pending_conflicts": state.pending_conflicts,

        "scope_filter": state.scope_filter,
        "show_conflicts_only": state.show_conflicts_only,

        "rows_total": total_rows,
        "rows_visible": row_data,
        "row_height": row_height,

        # Scroll state
        "scroll_y": target_scroll_y,
        "start_index": start_idx,

        # Selected details (for side panel)
        "selected_index": state.selected_index,
        "selected_item": _get_selected_details(rows, state.selected_index),

        # Runtime flags
        "is_web": is_web,
        "hint_text": _get_hint_text(state, is_web)
    }

def _get_selected_details(rows: tuple, index: int) -> dict[str, Any] | None:
    if 0 <= index < len(rows):
        row = rows[index]
        return {
            "title": row.title,
            "action_id": row.action_id,
            "scope": row.scope,
            "effective": row.shortcut_effective,
            "default": row.shortcut_default,
            "conflicts": row.conflict_ids,
            "has_override": row.has_override,
        }
    return None

def _get_hint_text(state: Any, is_web: bool) -> str:
    """Return context-sensitive hints."""
    if state.recording:
        return "RECORDING... Press key combo. ESC: Cancel."

    hints = ["Arrows: Nav", "Enter: Record", "Del: Reset", "F1: Scope", "F2: Conflicts"]

    if not is_web:
        hints.append("Ctrl+S: Apply & Save")
    else:
        hints.append("(Preview Only)")

    return " | ".join(hints)

