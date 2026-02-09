"""Mouse handling for context_menu scope."""
from __future__ import annotations

from typing import Any

from engine.input_runtime.capture_mouse_router_model import MouseEvent
from engine.input_runtime.capture_mouse_router_handlers_modal_base import dispatch_modal_mouse_base


def dispatch_context_menu_mouse(controller: Any, event: MouseEvent, action_id: str) -> bool:
    """Dispatch mouse event for context_menu scope.
    
    Context menus consume all mouse events to prevent click-through.
    """
    return dispatch_modal_mouse_base(controller, event, action_id)


__all__ = ["dispatch_context_menu_mouse"]
