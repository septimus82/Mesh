"""Mouse handling for authoring_selected scope (delegates to UI handlers)."""
from __future__ import annotations

from typing import Any

from engine.input_runtime.capture_mouse_router_model import MouseEvent
from engine.input_runtime.capture_mouse_router_handlers_modal_base import (
    maybe_handle_editor_mouse_press,
    maybe_handle_editor_mouse_release,
)


def dispatch_authoring_selected_mouse(controller: Any, event: MouseEvent, action_id: str) -> bool:
    """Dispatch mouse event for authoring_selected scope.
    
    This scope is active when an entity is selected in authoring mode.
    It delegates to UI handlers for property editing, transform handles, etc.
    """
    window = controller.window

    if action_id == "mouse.authoring_selected.press":
        return maybe_handle_editor_mouse_press(window, event)

    if action_id == "mouse.authoring_selected.release":
        return maybe_handle_editor_mouse_release(window, event)

    return False


__all__ = ["dispatch_authoring_selected_mouse"]
