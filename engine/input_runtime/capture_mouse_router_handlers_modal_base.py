"""Base mouse handling for modal UI scopes.

This module provides shared editor mouse handling used by all modal UI scopes.
Modal scopes (confirm_modal, context_menu, keybinds, etc.) consume all mouse
events to prevent click-through to the scene.
"""
from __future__ import annotations

from typing import Any

from engine.input_runtime.capture_mouse_router_model import MouseEvent


def maybe_handle_editor_mouse_press(window: Any, event: MouseEvent) -> bool:
    """Try to dispatch mouse press to the active editor controller.
    
    Returns True if the editor handled the event, False otherwise.
    """
    editor = getattr(window, "editor_controller", None)
    if editor is None or not getattr(editor, "active", False):
        return False
    handler = getattr(editor, "handle_mouse_press", None)
    if callable(handler) and handler(event.x, event.y, int(event.button or 0), int(event.modifiers)):
        return True
    click_handler = getattr(editor, "handle_mouse_click", None)
    if callable(click_handler) and click_handler(event.x, event.y, int(event.button or 0), int(event.modifiers)):
        return True
    return False


def maybe_handle_editor_mouse_release(window: Any, event: MouseEvent) -> bool:
    """Try to dispatch mouse release to the active editor controller.
    
    Returns True if the editor handled the event, False otherwise.
    """
    editor = getattr(window, "editor_controller", None)
    if editor is None or not getattr(editor, "active", False):
        return False
    handler = getattr(editor, "handle_mouse_release", None)
    if callable(handler) and handler(event.x, event.y, int(event.button or 0), int(event.modifiers)):
        return True
    return False


def dispatch_modal_mouse_base(controller: Any, event: MouseEvent, action_id: str) -> bool:
    """Base dispatcher for modal UI mouse events.
    
    All modal scopes consume mouse events to prevent click-through.
    Attempts to dispatch to editor if active, but always returns True.
    """
    window = controller.window
    if event.kind == "press":
        maybe_handle_editor_mouse_press(window, event)
    elif event.kind == "release":
        maybe_handle_editor_mouse_release(window, event)
    # Modals always consume mouse events
    return True


__all__ = [
    "dispatch_modal_mouse_base",
    "maybe_handle_editor_mouse_press",
    "maybe_handle_editor_mouse_release",
]
