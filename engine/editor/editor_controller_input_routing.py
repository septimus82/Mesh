from __future__ import annotations

from typing import Any


def set_last_mouse_pos(self, x: float, y: float):
    """Update the last known mouse position.

    DELEGATED to EditorCursorController.

    Args:
        x: Mouse X in screen coordinates.
        y: Mouse Y in screen coordinates.
    """
    self.cursor.update_mouse_pos(x, y)


def get_last_mouse_pos(self):
    """Get the last known mouse position.

    DELEGATED to EditorCursorController.

    Returns:
        Tuple of (x, y) in screen coordinates.
    """
    return self.cursor.get_last_mouse_pos()


def get_cursor_hint_text(self, window_w: int, window_h: int):
    """Get cursor hint text based on current editor state.

    DELEGATED to EditorCursorController.

    Args:
        window_w: Window width.
        window_h: Window height.

    Returns:
        Hint text string or None if no hint.
    """
    return self.cursor.get_cursor_hint_text(window_w, window_h)


def get_cursor_hint_kind(self, window_w: int, window_h: int):
    """Get cursor hint kind for cursor affordance.

    DELEGATED to EditorCursorController.

    Args:
        window_w: Window width.
        window_h: Window height.

    Returns:
        Cursor kind string or None when editor is inactive.
    """
    return self.cursor.get_cursor_hint_kind(window_w, window_h)


def _compute_cursor_hint(self, window_w: int, window_h: int):
    """Compute cursor hint. DELEGATED to EditorCursorController."""
    return self.cursor._compute_cursor_hint(window_w, window_h)

def bind_input_routing_methods(cls: Any) -> None:
    cls.set_last_mouse_pos = set_last_mouse_pos
    cls.get_last_mouse_pos = get_last_mouse_pos
    cls.get_cursor_hint_text = get_cursor_hint_text
    cls.get_cursor_hint_kind = get_cursor_hint_kind
    cls._compute_cursor_hint = _compute_cursor_hint
