"""Mouse handling for entity_select scope."""
from __future__ import annotations

from typing import Any

import engine.optional_arcade as optional_arcade

from engine.input_runtime.capture_mouse_router_model import MouseEvent
from engine.input_runtime.capture_mouse_router_handlers_modal_base import (
    maybe_handle_editor_mouse_press,
    maybe_handle_editor_mouse_release,
)
from engine.swallowed_exceptions import _log_swallow


def dispatch_entity_select_mouse(controller: Any, event: MouseEvent, action_id: str) -> bool:
    """Dispatch mouse event for entity_select scope."""
    window = controller.window

    if action_id == "mouse.entity_select.press":
        if maybe_handle_editor_mouse_press(window, event):
            return True
        return _handle_entity_select_mouse_press(window, event)

    if action_id == "mouse.entity_select.release":
        if maybe_handle_editor_mouse_release(window, event):
            return True
        return _handle_entity_select_mouse_release(window, event)

    if action_id == "mouse.entity_select.scroll":
        return _handle_entity_select_mouse_scroll(window, event)

    return False


def _handle_entity_select_mouse_press(window: Any, event: MouseEvent) -> bool:
    from engine.entity_select_mode import EntitySelectState, clear_drag, update_drag_rect, set_selection  # noqa: PLC0415

    state = getattr(window, "entity_select_state", None)
    if not (
        bool(getattr(window, "show_debug", False))
        and isinstance(state, EntitySelectState)
    ):
        return False
    if int(event.button or 0) != int(optional_arcade.arcade.MOUSE_BUTTON_LEFT):
        return True
    try:
        world_x, world_y = window.screen_to_world(float(event.x), float(event.y))
    except Exception:  # noqa: BLE001  # REASON: screen-to-world conversion failures should fall back to no entity-select click handling
        return True

    # Check if clicking on an entity via scene_inspector_overlay
    overlay = getattr(window, "scene_inspector_overlay", None)
    provider = getattr(overlay, "provider", None)
    clicked_entity_id = None
    if callable(provider):
        try:
            payload = provider(window)
            hover = payload.get("hover", {}) if isinstance(payload, dict) else {}
            clicked_entity_id = hover.get("id") if isinstance(hover, dict) else None
        except Exception:  # noqa: BLE001  # REASON: inspector hover payload queries are optional and should fall back to marquee selection behavior
            _log_swallow("CAPT-001", "engine/input_runtime/capture_mouse_router_handlers_entity_select.py pass-only blanket swallow")
            pass

    if clicked_entity_id:
        # Clicking on an entity: handle selection
        multi = bool(event.modifiers & optional_arcade.arcade.key.MOD_SHIFT)
        existing = list(state.selected_ids or [])
        if multi:
            # Shift-click: toggle membership
            if clicked_entity_id in existing:
                # Remove from selection (toggle off)
                existing = [eid for eid in existing if eid != clicked_entity_id]
                new_primary = existing[0] if existing else None
                set_selection(window, state, existing, primary_id=new_primary)
            else:
                # Add to selection
                existing.append(clicked_entity_id)
                set_selection(window, state, existing, primary_id=clicked_entity_id)
        elif clicked_entity_id in existing:
            # Clicking on already-selected entity: keep current multi-selection for group drag
            pass
        else:
            # Normal click on unselected entity: replace selection
            set_selection(window, state, [clicked_entity_id])
        # Start drag mode for potential move operations
        clear_drag(state)
        state.dragging = True
        state.drag_mode = "move"
        state.drag_anchor_world = (float(world_x), float(world_y))
    else:
        # Clicking on empty space: start marquee selection
        # Don't clear selection yet - let release decide based on modifiers
        clear_drag(state)
        state.dragging = True
        state.drag_mode = "marquee"
        state.drag_anchor_world = (float(world_x), float(world_y))
        update_drag_rect(state, world_x=float(world_x), world_y=float(world_y))

    return True


def _handle_entity_select_mouse_release(window: Any, event: MouseEvent) -> bool:
    from engine.entity_select_mode import (  # noqa: PLC0415
        EntitySelectState,
        clear_drag,
        set_selection,
        iter_entity_ids_in_world_rect,
    )

    state = getattr(window, "entity_select_state", None)
    if not (
        bool(getattr(window, "show_debug", False))
        and isinstance(state, EntitySelectState)
        and bool(getattr(state, "dragging", False))
    ):
        return False
    if int(event.button or 0) != int(optional_arcade.arcade.MOUSE_BUTTON_LEFT):
        return True

    try:
        world_x, world_y = window.screen_to_world(float(event.x), float(event.y))
    except Exception:  # noqa: BLE001  # REASON: screen-to-world conversion failures should clear drag state and skip entity-select release handling
        clear_drag(state)
        return True

    # Finish marquee selection
    rect = state.drag_rect_world
    if rect is not None and state.drag_mode == "marquee":
        shift_held = bool(event.modifiers & optional_arcade.arcade.key.MOD_SHIFT)
        ctrl_held = bool(event.modifiers & optional_arcade.arcade.key.MOD_CTRL)
        ids = list(iter_entity_ids_in_world_rect(window, rect))
        existing = list(state.selected_ids or [])
        
        if shift_held:
            # Union: add marquee entities to existing selection
            for eid in ids:
                if eid not in existing:
                    existing.append(eid)
            set_selection(window, state, existing)
        elif ctrl_held:
            # Subtract: remove marquee entities from existing selection
            remaining = [eid for eid in existing if eid not in ids]
            set_selection(window, state, remaining)
        else:
            # Replace: marquee entities become the selection
            set_selection(window, state, ids)

    clear_drag(state)
    return True


def _handle_entity_select_mouse_scroll(window: Any, event: MouseEvent) -> bool:
    from engine.entity_select_mode import EntitySelectState  # noqa: PLC0415

    state = getattr(window, "entity_select_state", None)
    if not (
        bool(getattr(window, "show_debug", False))
        and isinstance(state, EntitySelectState)
    ):
        return False

    return False  # Allow default scrolling behavior


__all__ = ["dispatch_entity_select_mouse"]
