"""Mouse handling for keybinds scope."""
from __future__ import annotations

from typing import Any

from engine.input_runtime.capture_mouse_router_model import MouseEvent
from engine.input_runtime.capture_mouse_router_handlers_modal_base import dispatch_modal_mouse_base


def dispatch_keybinds_mouse(controller: Any, event: MouseEvent, action_id: str) -> bool:
    """Dispatch mouse event for keybinds scope.
    
    Keybinds panel consumes all mouse events to prevent click-through.
    """
    return dispatch_modal_mouse_base(controller, event, action_id)


__all__ = ["dispatch_keybinds_mouse"]
