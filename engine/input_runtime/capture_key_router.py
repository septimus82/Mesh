"""Capture key router - resolves key combos to actions and dispatches them.

This module connects the pure model (capture_key_router_model) to the
runtime state. It builds focus snapshots, resolves routes, checks action
enablement, and dispatches actions.

The router does NOT contain any key handling logic - it only resolves
routes and dispatches them. All logic lives in the model or action handlers.
"""
from __future__ import annotations

from typing import Any

import engine.optional_arcade as optional_arcade

from engine.input_runtime.capture_runtime_focus_model import (
    CaptureFocusSnapshot,
    compute_active_scopes,
)
from engine.input_runtime.capture_key_router_model import (
    KeyCombo,
    RouteSpec,
    build_route_table,
    resolve_route,
)
from engine.input_runtime import capture_key_router_handlers_ui as ui_handlers
from engine.input_runtime import capture_key_router_handlers_palette as palette_handlers
from engine.input_runtime import capture_key_router_handlers_tile_paint as tile_paint_handlers
from engine.input_runtime import capture_key_router_handlers_entity_paint as entity_paint_handlers
from engine.input_runtime import capture_key_router_handlers_entity_select as entity_select_handlers
from engine.input_runtime import capture_key_router_handlers_authoring as authoring_handlers
from engine.input_runtime import capture_key_router_handlers_editor as editor_handlers
from engine.input_runtime import capture_key_router_handlers_global as global_handlers


# Cache the route table for performance
_ROUTE_TABLE: tuple[RouteSpec, ...] | None = None


def _get_route_table() -> tuple[RouteSpec, ...]:
    """Get the cached route table, building it if necessary."""
    global _ROUTE_TABLE
    if _ROUTE_TABLE is None:
        _ROUTE_TABLE = build_route_table()
    return _ROUTE_TABLE


def route_and_dispatch(controller: Any, key: int, modifiers: int, snapshot: CaptureFocusSnapshot) -> bool:
    """Route a key press to an action and dispatch it.

    This is the main entry point for the key router. It:
    1. Receives a focus snapshot from the caller
    2. Computes the active scopes
    3. Resolves the route using the model
    4. Dispatches the action if found

    Args:
        controller: The InputController instance.
        key: The key code pressed.
        modifiers: The modifier flags.
        snapshot: The precomputed focus snapshot.

    Returns:
        True if the key was consumed, False otherwise.
    """
    combo = KeyCombo(key=int(key), mods=int(modifiers))

    active_scopes = compute_active_scopes(snapshot)
    routes = _get_route_table()
    action_id = resolve_route(active_scopes, combo, routes, snapshot)

    if action_id is None:
        if global_handlers.is_interact_key(controller, key):
            return bool(_dispatch_action(controller, "capture.interact.primary", snapshot, key=key, modifiers=modifiers))
        return False

    return bool(_dispatch_action(controller, action_id, snapshot, key=key, modifiers=modifiers))


def handle_unmapped_key(_controller: Any, _key: int, _modifiers: int) -> bool:
    """Legacy shim: no unmapped keys remain."""
    return False


# ---------------------------------------------------------------------------
# Action dispatcher
# ---------------------------------------------------------------------------

def _dispatch_action(
    controller: Any,
    action_id: str,
    snapshot: CaptureFocusSnapshot,
    *,
    key: int | None = None,
    modifiers: int | None = None,
) -> bool:
    """Dispatch an action by ID."""
    window = controller.window

    if action_id.startswith(
        (
            "capture.confirm_modal.",
            "capture.context_menu.",
            "capture.keybinds.",
            "capture.inline_rename.",
            "capture.command_palette.",
            "capture.console.",
            "capture.project_explorer.",
            "capture.problems.",
        )
    ):
        return ui_handlers.dispatch_ui_action(
            window,
            snapshot,
            action_id,
            key=key,
            modifiers=modifiers,
        )

    if action_id.startswith(("capture.palette_mode.", "capture.capture_mode.")):
        return palette_handlers.dispatch_palette_action(window, snapshot, action_id)

    if action_id.startswith("capture.tile_paint."):
        return tile_paint_handlers.dispatch_tile_paint_action(window, action_id)

    if action_id.startswith("capture.entity_paint."):
        return entity_paint_handlers.dispatch_entity_paint_action(window, snapshot, action_id)

    if action_id.startswith("capture.entity_select."):
        return entity_select_handlers.dispatch_entity_select_action(window, snapshot, action_id)

    if action_id.startswith("capture.authoring."):
        return authoring_handlers.dispatch_authoring_action(window, action_id)

    if action_id.startswith("capture.editor."):
        return editor_handlers.dispatch_editor_action(window, action_id)

    return global_handlers.dispatch_global_action(
        controller,
        snapshot,
        action_id,
        key=key,
        modifiers=modifiers,
    )


# Re-export for backward compatibility (used by old capture_key_router.py)
__all__ = [
    "route_and_dispatch",
    "KeyCombo",
]
