"""Mouse handling for command_palette scope."""
from __future__ import annotations

from typing import Any

from engine.input_runtime.capture_mouse_router_handlers_modal_base import dispatch_modal_mouse_base
from engine.input_runtime.capture_mouse_router_model import MouseEvent


def dispatch_command_palette_mouse(controller: Any, event: MouseEvent, action_id: str) -> bool:
    """Dispatch mouse event for command_palette scope.
    
    Command palette consumes all mouse events to prevent click-through.
    """
    return dispatch_modal_mouse_base(controller, event, action_id)


__all__ = ["dispatch_command_palette_mouse"]
