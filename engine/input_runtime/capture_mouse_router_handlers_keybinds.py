"""Mouse handling for keybinds scope."""
from __future__ import annotations

from typing import Any

from engine.input_runtime.capture_mouse_router_model import MouseEvent


def dispatch_keybinds_mouse(controller: Any, event: MouseEvent, action_id: str) -> bool:  # noqa: ARG001
    """Dispatch mouse event for keybinds scope.

    Keybinds panel consumes all mouse events to prevent click-through.
    It forwards click/scroll to the keybinds controller when available.
    """
    window = controller.window
    editor = getattr(window, "editor_controller", None)
    keybinds = getattr(editor, "keybinds", None) if editor is not None else None
    if keybinds is not None:
        if event.kind == "press":
            handler = getattr(keybinds, "handle_mouse_press", None)
            if callable(handler):
                handler(event.x, event.y, int(event.button or 0), int(event.modifiers))
        elif event.kind == "scroll":
            handler = getattr(keybinds, "handle_mouse_scroll", None)
            if callable(handler):
                handler(event.x, event.y, event.scroll_x, event.scroll_y)
    return True


__all__ = ["dispatch_keybinds_mouse"]
