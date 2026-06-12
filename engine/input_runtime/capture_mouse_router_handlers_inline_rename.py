"""Mouse handling for inline_rename scope."""
from __future__ import annotations

from typing import Any

from engine.input_runtime.capture_mouse_router_handlers_modal_base import dispatch_modal_mouse_base
from engine.input_runtime.capture_mouse_router_model import MouseEvent


def dispatch_inline_rename_mouse(controller: Any, event: MouseEvent, action_id: str) -> bool:
    """Dispatch mouse event for inline_rename scope.
    
    Inline rename consumes all mouse events to prevent click-through.
    """
    return dispatch_modal_mouse_base(controller, event, action_id)


__all__ = ["dispatch_inline_rename_mouse"]
