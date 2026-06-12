"""Capture mouse router - resolves mouse events to actions and dispatches them.

This is a glue-only module. It:
1. Builds and caches the mouse route table
2. Resolves mouse events to action IDs via the route table
3. Dispatches actions to the appropriate handler module via prefix registry

All handler logic lives in the handler modules. This module must not contain:
- Per-action logic
- Coordinate math
- State mutation (beyond calling handlers)

-------------------------------------------------------------------------------
DEVELOPER NOTES (02:00 AM reference)
-------------------------------------------------------------------------------

WHERE TO ADD NEW HANDLERS:
  New mouse handlers go in per-scope modules, NOT here. Pattern:
    capture_mouse_router_handlers_<scope>.py  (e.g., _tile_paint, _entity_select)
  Then add a prefix entry in MOUSE_PREFIX_DISPATCH below.

VALIDATION:
  build_mouse_routes() calls validate_route_table() before returning.
  This is MANDATORY - if validation fails, the route table is broken.
  Tests also call validate_route_table() directly for schema checks.

SHIM DEPRECATION:
  The old monolithic shims (capture_mouse_router_handlers_paint.py and
  capture_mouse_router_handlers_select.py) are FROZEN and DEPRECATED.
  They exist only for backward compatibility. Never add code to them.
  A policy test enforces no new shim modules are created.
-------------------------------------------------------------------------------
"""
from __future__ import annotations

from typing import Any, Callable

from engine.input_runtime import capture_mouse_router_handlers_authoring_selected as authoring_selected_handlers

# Paint mode scopes (split from monolithic paint handlers)
from engine.input_runtime import capture_mouse_router_handlers_capture_mode as capture_mode_handlers
from engine.input_runtime import capture_mouse_router_handlers_command_palette as command_palette_handlers

# Import handler modules - UI modal scopes
from engine.input_runtime import capture_mouse_router_handlers_confirm_modal as confirm_modal_handlers
from engine.input_runtime import capture_mouse_router_handlers_console as console_handlers
from engine.input_runtime import capture_mouse_router_handlers_context_menu as context_menu_handlers
from engine.input_runtime import capture_mouse_router_handlers_entity_paint as entity_paint_handlers

# Select mode scopes (split from monolithic select handlers)
from engine.input_runtime import capture_mouse_router_handlers_entity_select as entity_select_handlers

# Global fallback
from engine.input_runtime import capture_mouse_router_handlers_global as global_handlers
from engine.input_runtime import capture_mouse_router_handlers_inline_rename as inline_rename_handlers
from engine.input_runtime import capture_mouse_router_handlers_keybinds as keybinds_handlers
from engine.input_runtime import capture_mouse_router_handlers_problems as problems_handlers
from engine.input_runtime import capture_mouse_router_handlers_project_explorer as project_explorer_handlers
from engine.input_runtime import capture_mouse_router_handlers_tile_paint as tile_paint_handlers
from engine.input_runtime.capture_mouse_router_model import MouseEvent, MouseRouteSpec, build_mouse_routes, resolve_mouse_route
from engine.input_runtime.capture_runtime_focus_model import CaptureFocusSnapshot, compute_active_scopes

# ---------------------------------------------------------------------------
# Route table cache
# ---------------------------------------------------------------------------

_MOUSE_ROUTES: tuple[MouseRouteSpec, ...] | None = None


def _get_routes() -> tuple[MouseRouteSpec, ...]:
    global _MOUSE_ROUTES
    if _MOUSE_ROUTES is None:
        _MOUSE_ROUTES = build_mouse_routes()
    return _MOUSE_ROUTES


# ---------------------------------------------------------------------------
# Prefix dispatch registry - sorted longest-prefix-first for determinism
# ---------------------------------------------------------------------------

# Type alias for handler functions
MouseHandler = Callable[[Any, MouseEvent, str], bool]

# Registry of (prefix, module, function_name) tuples, sorted longest-prefix-first
# First match wins - this ensures deterministic routing
# Using (module, func_name) allows monkeypatching in tests
MOUSE_PREFIX_DISPATCH: tuple[tuple[str, str, str], ...] = (
    # Modal UI scopes (longest prefixes first if nested)
    ("mouse.confirm_modal", "capture_mouse_router_handlers_confirm_modal", "dispatch_confirm_modal_mouse"),
    ("mouse.context_menu", "capture_mouse_router_handlers_context_menu", "dispatch_context_menu_mouse"),
    ("mouse.keybinds", "capture_mouse_router_handlers_keybinds", "dispatch_keybinds_mouse"),
    ("mouse.inline_rename", "capture_mouse_router_handlers_inline_rename", "dispatch_inline_rename_mouse"),
    ("mouse.command_palette", "capture_mouse_router_handlers_command_palette", "dispatch_command_palette_mouse"),
    ("mouse.console", "capture_mouse_router_handlers_console", "dispatch_console_mouse"),
    ("mouse.project_explorer", "capture_mouse_router_handlers_project_explorer", "dispatch_project_explorer_mouse"),
    ("mouse.problems", "capture_mouse_router_handlers_problems", "dispatch_problems_mouse"),
    # Paint modes - each scope has its own handler module
    ("mouse.capture_mode.", "capture_mouse_router_handlers_capture_mode", "dispatch_capture_mode_mouse"),
    ("mouse.tile_paint.", "capture_mouse_router_handlers_tile_paint", "dispatch_tile_paint_mouse"),
    ("mouse.entity_paint.", "capture_mouse_router_handlers_entity_paint", "dispatch_entity_paint_mouse"),
    # Select modes - each scope has its own handler module
    ("mouse.entity_select.", "capture_mouse_router_handlers_entity_select", "dispatch_entity_select_mouse"),
    ("mouse.authoring_selected.", "capture_mouse_router_handlers_authoring_selected", "dispatch_authoring_selected_mouse"),
    # Global fallback (shortest prefix, must be last)
    ("mouse.global", "capture_mouse_router_handlers_global", "dispatch_global_mouse"),
)

# Module cache for late binding
_HANDLER_MODULES: dict[str, Any] = {
    "capture_mouse_router_handlers_confirm_modal": confirm_modal_handlers,
    "capture_mouse_router_handlers_context_menu": context_menu_handlers,
    "capture_mouse_router_handlers_keybinds": keybinds_handlers,
    "capture_mouse_router_handlers_inline_rename": inline_rename_handlers,
    "capture_mouse_router_handlers_command_palette": command_palette_handlers,
    "capture_mouse_router_handlers_console": console_handlers,
    "capture_mouse_router_handlers_project_explorer": project_explorer_handlers,
    "capture_mouse_router_handlers_problems": problems_handlers,
    "capture_mouse_router_handlers_capture_mode": capture_mode_handlers,
    "capture_mouse_router_handlers_tile_paint": tile_paint_handlers,
    "capture_mouse_router_handlers_entity_paint": entity_paint_handlers,
    "capture_mouse_router_handlers_entity_select": entity_select_handlers,
    "capture_mouse_router_handlers_authoring_selected": authoring_selected_handlers,
    "capture_mouse_router_handlers_global": global_handlers,
}


def _get_handler(module_name: str, func_name: str) -> MouseHandler:
    """Get handler function with late binding (allows monkeypatching)."""
    module = _HANDLER_MODULES[module_name]
    handler: MouseHandler = getattr(module, func_name)
    return handler


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def route_and_dispatch_mouse(controller: Any, event: MouseEvent, snapshot: CaptureFocusSnapshot) -> bool:
    """Route a mouse event to an action and dispatch it.
    
    Returns True if the event was handled, False otherwise.
    """
    active_scopes = compute_active_scopes(snapshot)
    routes = _get_routes()
    action_id = resolve_mouse_route(active_scopes, event, routes, snapshot)
    if action_id is None:
        return False
    return bool(_dispatch_mouse_action(controller, event, action_id))


def _dispatch_mouse_action(controller: Any, event: MouseEvent, action_id: str) -> bool:
    """Dispatch a mouse action using the prefix registry.
    
    First matching prefix wins. Registry is sorted longest-prefix-first
    to ensure deterministic behavior with nested prefixes.
    """
    for prefix, module_name, func_name in MOUSE_PREFIX_DISPATCH:
        if action_id.startswith(prefix) or action_id == prefix:
            handler = _get_handler(module_name, func_name)
            return handler(controller, event, action_id)
    # No handler matched - should not happen if registry is complete
    return False


__all__ = ["route_and_dispatch_mouse", "MOUSE_PREFIX_DISPATCH"]
