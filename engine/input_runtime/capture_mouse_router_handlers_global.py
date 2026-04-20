from __future__ import annotations

from typing import Any

from engine.input_runtime.capture_mouse_router_model import MouseEvent
from engine.input_runtime import capture_mouse_router_handlers_ui as ui_handlers
from engine.swallowed_exceptions import _log_swallow


def dispatch_global_mouse(controller: Any, event: MouseEvent, action_id: str) -> bool:
    if action_id != "mouse.global":
        return False
    window = controller.window
    
    if event.kind == "press":
        # First try editor (if active)
        if ui_handlers.maybe_handle_editor_mouse_press(window, event):
            return True
        # Fall back to entity selection in debug mode (even if editor not active)
        return _maybe_handle_debug_entity_select_press(window, event)
    
    if event.kind == "release":
        # First try editor (if active)
        if ui_handlers.maybe_handle_editor_mouse_release(window, event):
            return True
        # Fall back to entity selection in debug mode (even if editor not active)
        return _maybe_handle_debug_entity_select_release(window, event)
    
    return False


def _maybe_handle_debug_entity_select_press(window: Any, event: MouseEvent) -> bool:
    """Handle mouse press for entity selection when in debug mode but editor not active.
    
    This allows entity selection to be initiated even when the editor is not active,
    as long as show_debug is True and entity_select_state exists.
    """
    if not bool(getattr(window, "show_debug", False)):
        return False
    
    from engine.entity_select_mode import EntitySelectState, clear_drag, update_drag_rect, set_selection  # noqa: PLC0415
    import engine.optional_arcade as optional_arcade  # noqa: PLC0415
    
    state = getattr(window, "entity_select_state", None)
    if not isinstance(state, EntitySelectState):
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
            _log_swallow("CAPT-001", "engine/input_runtime/capture_mouse_router_handlers_global.py pass-only blanket swallow")
            pass
    
    if clicked_entity_id:
        # Clicking on an entity: select it immediately
        multi = bool(event.modifiers & optional_arcade.arcade.key.MOD_SHIFT)
        if multi:
            # Shift-click: toggle membership
            existing = list(state.selected_ids or [])
            if clicked_entity_id in existing:
                # Remove from selection (toggle off)
                existing = [eid for eid in existing if eid != clicked_entity_id]
                new_primary = existing[0] if existing else None
                set_selection(window, state, existing, primary_id=new_primary)
            else:
                # Add to selection
                existing.append(clicked_entity_id)
                set_selection(window, state, existing, primary_id=clicked_entity_id)
        else:
            set_selection(window, state, [clicked_entity_id])
        # Still start drag mode for potential move operations
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


def _maybe_handle_debug_entity_select_release(window: Any, event: MouseEvent) -> bool:
    """Handle mouse release for entity selection when in debug mode but editor not active."""
    if not bool(getattr(window, "show_debug", False)):
        return False
    
    from engine.entity_select_mode import (  # noqa: PLC0415
        EntitySelectState,
        clear_drag,
        set_selection,
        iter_entity_ids_in_world_rect,
    )
    import engine.optional_arcade as optional_arcade  # noqa: PLC0415
    
    state = getattr(window, "entity_select_state", None)
    if not (
        isinstance(state, EntitySelectState)
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
    
    # Check if this was a point-click (not a drag) by looking at rect size
    rect = state.drag_rect_world
    is_point_click = False
    if rect is not None:
        x0, y0, x1, y1 = rect
        # If rect is very small (< 5 pixels in both dimensions), treat as point-click
        is_point_click = abs(x1 - x0) < 5 and abs(y1 - y0) < 5
    
    if is_point_click:
        # Point-click: select entity under cursor using scene_inspector_overlay
        overlay = getattr(window, "scene_inspector_overlay", None)
        provider = getattr(overlay, "provider", None)
        if callable(provider):
            try:
                payload = provider(window)
                hover = payload.get("hover", {}) if isinstance(payload, dict) else {}
                entity_id = hover.get("id") if isinstance(hover, dict) else None
                if entity_id:
                    multi = bool(event.modifiers & optional_arcade.arcade.key.MOD_SHIFT)
                    if multi:
                        existing = list(state.selected_ids or [])
                        if entity_id not in existing:
                            existing.append(entity_id)
                        set_selection(window, state, existing, primary_id=entity_id)
                    else:
                        set_selection(window, state, [entity_id])
                else:
                    # Click on empty space clears selection
                    multi = bool(event.modifiers & optional_arcade.arcade.key.MOD_SHIFT)
                    if not multi:
                        set_selection(window, state, [])
            except Exception:  # noqa: BLE001  # REASON: inspector hover payload queries are optional and should fall back to existing release selection behavior
                _log_swallow("CAPT-002", "engine/input_runtime/capture_mouse_router_handlers_global.py pass-only blanket swallow")
                pass
    else:
        # Marquee selection: use rect to find entities
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


__all__ = ["dispatch_global_mouse"]
