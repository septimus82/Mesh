"""DEPRECATED: Monolithic select handlers - replaced by per-scope modules.

This module is a stub for backward compatibility. It re-exports dispatch functions
from the new per-scope modules and emits a DeprecationWarning on import.

New code MUST use the per-scope handler modules directly:
- capture_mouse_router_handlers_entity_select.py
- capture_mouse_router_handlers_authoring_selected.py

This module will be removed in a future version.
"""
from __future__ import annotations

import warnings
from typing import Any

from engine.input_runtime.capture_mouse_router_model import MouseEvent

# Emit deprecation warning on import
warnings.warn(
    "capture_mouse_router_handlers_select is deprecated and will be removed. "
    "Use entity_select and authoring_selected handler modules instead.",
    DeprecationWarning,
    stacklevel=2,
)


def dispatch_select_mouse(controller: Any, event: MouseEvent, action_id: str) -> bool:
    """DEPRECATED: Dispatch select mouse event - delegates to per-scope modules."""
    # Late import to avoid circular dependency
    if action_id.startswith("mouse.entity_select."):
        from engine.input_runtime.capture_mouse_router_handlers_entity_select import dispatch_entity_select_mouse
        return dispatch_entity_select_mouse(controller, event, action_id)
    if action_id.startswith("mouse.authoring_selected."):
        from engine.input_runtime.capture_mouse_router_handlers_authoring_selected import dispatch_authoring_selected_mouse
        return dispatch_authoring_selected_mouse(controller, event, action_id)
    return False


__all__ = ["dispatch_select_mouse"]
