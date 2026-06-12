"""Legacy UI mouse handlers - delegates to modal-specific modules.

This module is kept for backward compatibility. New code should import
from the specific handler modules (capture_mouse_router_handlers_confirm_modal, etc.)
or from capture_mouse_router_handlers_modal_base for shared utilities.
"""
from __future__ import annotations

from typing import Any

# Re-export from modal_base for backward compatibility
from engine.input_runtime.capture_mouse_router_handlers_modal_base import (
    dispatch_modal_mouse_base,
    maybe_handle_editor_mouse_press,
    maybe_handle_editor_mouse_release,
)
from engine.input_runtime.capture_mouse_router_model import MouseEvent


def dispatch_ui_mouse(controller: Any, event: MouseEvent, action_id: str) -> bool:
    """Legacy dispatcher - delegates to modal base.
    
    Deprecated: Use the specific handler modules directly.
    """
    return dispatch_modal_mouse_base(controller, event, action_id)


__all__ = [
    "dispatch_ui_mouse",
    "maybe_handle_editor_mouse_press",
    "maybe_handle_editor_mouse_release",
]
