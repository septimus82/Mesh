"""DEPRECATED: Monolithic paint handlers - replaced by per-scope modules.

This module is a stub for backward compatibility. It re-exports dispatch functions
from the new per-scope modules and emits a DeprecationWarning on import.

New code MUST use the per-scope handler modules directly:
- capture_mouse_router_handlers_capture_mode.py
- capture_mouse_router_handlers_tile_paint.py  
- capture_mouse_router_handlers_entity_paint.py

This module will be removed in a future version.
"""
from __future__ import annotations

import warnings
from typing import Any

from engine.input_runtime.capture_mouse_router_model import MouseEvent

# Emit deprecation warning on import
warnings.warn(
    "capture_mouse_router_handlers_paint is deprecated and will be removed. "
    "Use capture_mode, tile_paint, and entity_paint handler modules instead.",
    DeprecationWarning,
    stacklevel=2,
)


def dispatch_paint_mouse(controller: Any, event: MouseEvent, action_id: str) -> bool:
    """DEPRECATED: Dispatch paint mouse event - delegates to per-scope modules."""
    # Late import to avoid circular dependency
    if action_id.startswith("mouse.capture_mode."):
        from engine.input_runtime.capture_mouse_router_handlers_capture_mode import dispatch_capture_mode_mouse
        return dispatch_capture_mode_mouse(controller, event, action_id)
    if action_id.startswith("mouse.tile_paint."):
        from engine.input_runtime.capture_mouse_router_handlers_tile_paint import dispatch_tile_paint_mouse
        return dispatch_tile_paint_mouse(controller, event, action_id)
    if action_id.startswith("mouse.entity_paint."):
        from engine.input_runtime.capture_mouse_router_handlers_entity_paint import dispatch_entity_paint_mouse
        return dispatch_entity_paint_mouse(controller, event, action_id)
    return False


__all__ = ["dispatch_paint_mouse"]
