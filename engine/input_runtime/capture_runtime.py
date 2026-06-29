"""Capture runtime - input handling entry points.

This module provides the entry points for handling input events in the
capture/authoring system. The key routing logic has been refactored into:

- capture_runtime_focus_model.py - Pure focus state model
- capture_key_router_model.py - Route table and resolution
- capture_key_router.py - Action dispatch

The handle_key_press function is now a thin wrapper that:
1. Calls the router for key handling
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import engine.optional_arcade as optional_arcade
from engine.input_runtime import capture_key_router as router
from engine.input_runtime import capture_mouse_router as mouse_router
from engine.input_runtime.capture_focus_query import get_capture_focus_snapshot
from engine.input_runtime.capture_mouse_router_model import MouseEvent
from engine.swallowed_exceptions import _log_swallow

if TYPE_CHECKING:
    from engine.input_controller import InputController


def ui_blocks_input(controller: "InputController") -> bool:
    """Check if UI is blocking input."""
    ui_ctrl = getattr(controller.window, "ui_controller", None)
    return bool(ui_ctrl and getattr(ui_ctrl, "input_blocked", False))


def player_input_blocked(controller: "InputController") -> bool:
    """Check if player input is blocked (dialogue, etc.)."""
    window = controller.window
    ui_ctrl = getattr(window, "ui_controller", None)
    if ui_ctrl and getattr(ui_ctrl, "input_blocked", False):
        return True
    dialogue = getattr(window, "dialogue_controller", None)
    if dialogue and getattr(dialogue, "active", False):
        return True
    return False


def handle_key_press(controller: "InputController", key: int, modifiers: int) -> bool:
    """Handle key press events with capture priority.

    Returns True if the event was consumed and should not propagate further.

    This function routes keys through the capture_key_router system first.
    """
    window = controller.window
    try:
        setattr(window, "_debug_last_modifiers", int(modifiers))
    except Exception:  # noqa: BLE001  # REASON: capture runtime fallback isolation
        _log_swallow("CAPT-001", "engine/input_runtime/capture_runtime.py pass-only blanket swallow")
        pass

    # -------------------------------------------------------------------------
    # PRIMARY ROUTING - via capture_key_router
    # Handles: confirm_modal, context_menu, keybinds, inline_rename,
    # command_palette, console, project_explorer, problems, palette_mode,
    # capture_mode, entity_paint, entity_select, and most global keys
    # -------------------------------------------------------------------------
    snapshot = get_capture_focus_snapshot(controller, modifiers)
    if router.route_and_dispatch(controller, key, modifiers, snapshot):
        return True

    # -------------------------------------------------------------------------
    # COMMAND PALETTE BLOCK
    # When command palette is open, block all other input (text handled by handle_text)
    # -------------------------------------------------------------------------
    if bool(getattr(window, "show_debug", False)) and getattr(window, "command_palette_enabled", False) is True:
        return True

    # -------------------------------------------------------------------------
    # CONSOLE PASS-THROUGH
    # Console handles its own key processing
    # -------------------------------------------------------------------------
    if window.console_controller.active:
        if window.console_controller.process_key(key, modifiers):
            return True

    # -------------------------------------------------------------------------
    # UI CONTROLLER PASS-THROUGH
    # Forward to UIController for menu handling
    # -------------------------------------------------------------------------
    if window.ui_controller.on_key_press(key, modifiers):
        return True

    # -------------------------------------------------------------------------
    # FALLBACK: Record key press for InputManager
    # -------------------------------------------------------------------------
    manager = getattr(controller, "manager", None)
    press = getattr(manager, "press", None) if manager is not None else None
    if callable(press):
        press(key)
    keys = getattr(controller, "_keys", None)
    if isinstance(keys, set):
        keys.add(key)
    return False


# ---------------------------------------------------------------------------
# Other input handlers
# ---------------------------------------------------------------------------

def handle_key_release(controller: "InputController", key: int, modifiers: int) -> bool:  # noqa: ARG001
    """Handle key release events."""
    manager = getattr(controller, "manager", None)
    release = getattr(manager, "release", None) if manager is not None else None
    if callable(release):
        release(key)
    keys = getattr(controller, "_keys", None)
    if isinstance(keys, set):
        keys.discard(key)
    return False


def handle_mouse_press(controller: "InputController", x: float, y: float, button: int, modifiers: int) -> bool:
    window = controller.window
    try:
        setattr(window, "_debug_last_modifiers", int(modifiers))
    except Exception:  # noqa: BLE001  # REASON: capture runtime fallback isolation
        _log_swallow("CAPT-002", "engine/input_runtime/capture_runtime.py pass-only blanket swallow")
        pass
    controller._mouse_x = float(x)
    controller._mouse_y = float(y)
    setattr(window, "_mouse_x", float(x))
    setattr(window, "_mouse_y", float(y))

    ui_controller = getattr(window, "ui_controller", None)
    ui_mouse = getattr(ui_controller, "on_mouse_press", None) if ui_controller is not None else None
    if callable(ui_mouse) and ui_mouse(float(x), float(y), int(button), int(modifiers)):
        return True

    event = MouseEvent(kind="press", button=int(button), x=float(x), y=float(y), modifiers=int(modifiers))
    snapshot = get_capture_focus_snapshot(controller, modifiers)
    return mouse_router.route_and_dispatch_mouse(controller, event, snapshot)


def handle_mouse_release(controller: "InputController", x: float, y: float, button: int, modifiers: int) -> bool:
    window = controller.window
    try:
        setattr(window, "_debug_last_modifiers", int(modifiers))
    except Exception:  # noqa: BLE001  # REASON: capture runtime fallback isolation
        _log_swallow("CAPT-003", "engine/input_runtime/capture_runtime.py pass-only blanket swallow")
        pass
    event = MouseEvent(kind="release", button=int(button), x=float(x), y=float(y), modifiers=int(modifiers))
    snapshot = get_capture_focus_snapshot(controller, modifiers)
    return mouse_router.route_and_dispatch_mouse(controller, event, snapshot)


def handle_mouse_scroll(controller: "InputController", x: float, y: float, scroll_x: float, scroll_y: float) -> bool:  # noqa: ARG001
    window = controller.window
    editor = getattr(window, "editor_controller", None)
    if editor is not None and getattr(editor, "active", False) and getattr(editor, "_find_everything_open", False):
        search = getattr(editor, "search", None)
        handler = getattr(search, "handle_find_everything_mouse_scroll", None)
        if callable(handler) and handler(float(x), float(y), float(scroll_x), float(scroll_y)):
            return True
    if editor is not None and getattr(editor, "active", False):
        overlay = getattr(window, "ai_chat_overlay", None)
        handler = getattr(overlay, "on_mouse_scroll", None) if overlay is not None else None
        if callable(handler) and handler(float(x), float(y), float(scroll_x), float(scroll_y)):
            return True
    if editor is not None and getattr(editor, "active", False):
        project_actions = getattr(editor, "project_explorer_actions", None)
        handler = getattr(project_actions, "handle_mouse_scroll", None) if project_actions is not None else None
        if callable(handler) and handler(float(x), float(y), float(scroll_x), float(scroll_y)):
            return True
    if editor is not None and getattr(editor, "active", False):
        scene_browse = getattr(editor, "scene_browse", None)
        handler = getattr(scene_browse, "handle_scene_browser_mouse_scroll", None) if scene_browse is not None else None
        if callable(handler) and handler(float(x), float(y), float(scroll_x), float(scroll_y)):
            return True
    if editor is not None and getattr(editor, "active", False):
        asset_browser = getattr(editor, "asset_browser", None)
        handler = getattr(asset_browser, "handle_asset_browser_mouse_scroll", None) if asset_browser is not None else None
        if callable(handler) and handler(float(x), float(y), float(scroll_x), float(scroll_y)):
            return True
    modifiers = int(getattr(window, "_debug_last_modifiers", 0) or 0)
    event = MouseEvent(
        kind="scroll",
        button=None,
        x=float(x),
        y=float(y),
        scroll_x=float(scroll_x),
        scroll_y=float(scroll_y),
        modifiers=modifiers,
    )
    snapshot = get_capture_focus_snapshot(controller, modifiers)
    return mouse_router.route_and_dispatch_mouse(controller, event, snapshot)


def handle_text(controller: "InputController", text: str) -> None:
    window = controller.window
    if bool(getattr(window, "show_debug", False)) and getattr(window, "command_palette_enabled", False) is True:
        if bool(getattr(window, "command_palette_prompt_active", False)):
            prompt_kind = str(getattr(window, "command_palette_prompt_kind", "text") or "text").strip().lower()
            attr = "command_palette_prompt_query" if prompt_kind == "pick" else "command_palette_prompt_text"
            t = str(getattr(window, attr, "") or "")
            for ch in str(text or ""):
                if ch in ("\n", "\r"):
                    continue
                if ch.isprintable():
                    t += ch
            if len(t) > 200:
                t = t[-200:]
            setattr(window, attr, t)
            if prompt_kind == "text":
                window.command_palette_prompt_index = 0
                from engine.command_palette_controller import handle_command_palette_prompt_text_changed  # noqa: PLC0415

                handle_command_palette_prompt_text_changed(window)
            return

        q = str(getattr(window, "command_palette_query", "") or "")
        for ch in str(text or ""):
            if ch.isalnum() or ch == " ":
                q += ch
        if len(q) > 80:
            q = q[-80:]
        window.command_palette_query = q
        window.command_palette_index = 0
        return
    if window.console_controller.active:
        # Filter out control characters (like backspace \x08) that might be sent
        # alongside the key event, to avoid double-handling or corrupting the buffer.
        filtered = "".join(ch for ch in text if ord(ch) >= 32 and ch != "\x7f")
        if filtered:
            controller.manager.feed_text(filtered)
        return

    editor = getattr(window, "editor_controller", None)
    if editor and getattr(editor, "active", False):
        handler = getattr(editor, "on_text", None)
        if callable(handler):
            if handler(text):
                return

    main_menu = getattr(window, "main_menu_overlay", None)
    if main_menu is not None and getattr(main_menu, "visible", False):
        handler = getattr(main_menu, "on_text", None)
        if callable(handler):
            handler(text)
        return

    browser = getattr(window, "dev_browser_overlay", None)
    if browser is not None and getattr(browser, "visible", False):
        handler = getattr(browser, "on_text", None)
        if callable(handler):
            handler(text)
        return

    if window.editor_controller.active:
        window.editor_controller.handle_text_input(text)


def handle_mouse_motion(controller: "InputController", x: float, y: float, dx: float, dy: float) -> None:  # noqa: ARG001
    """Handle mouse motion events."""
    controller._mouse_x = float(x)
    controller._mouse_y = float(y)
    setattr(controller.window, "_mouse_x", float(x))
    setattr(controller.window, "_mouse_y", float(y))

    editor_controller = getattr(controller.window, "editor_controller", None)
    if editor_controller is not None and getattr(editor_controller, "active", False):
        from engine.editor_runtime.hover_detection import update_hover_state  # noqa: PLC0415
        from engine.editor_runtime.input import handle_context_menu_motion, handle_menu_bar_motion  # noqa: PLC0415

        handle_menu_bar_motion(editor_controller, x, y)
        handle_context_menu_motion(editor_controller, x, y)

        window_w = getattr(controller.window, "width", 1280)
        window_h = getattr(controller.window, "height", 720)
        update_hover_state(editor_controller, x, y, window_w, window_h)

        set_mouse_pos = getattr(editor_controller, "set_last_mouse_pos", None)
        if callable(set_mouse_pos):
            set_mouse_pos(x, y)

        try:
            from engine.editor.editor_cursor_apply import apply_editor_cursor  # noqa: PLC0415
            get_kind = getattr(editor_controller, "get_cursor_hint_kind", None)
            if callable(get_kind):
                cursor_kind = str(get_kind(window_w, window_h) or "")
                apply_editor_cursor(controller.window, cursor_kind or None)
        except Exception:  # noqa: BLE001  # REASON: capture runtime fallback isolation
            _log_swallow("CAPT-004", "engine/input_runtime/capture_runtime.py pass-only blanket swallow")
            pass


def handle_mouse_drag(
    controller: "InputController",
    x: float,
    y: float,
    dx: float,
    dy: float,
    buttons: int,
    modifiers: int,
) -> None:
    """Handle mouse drag events."""
    controller._mouse_x = float(x)
    controller._mouse_y = float(y)
    setattr(controller.window, "_mouse_x", float(x))
    setattr(controller.window, "_mouse_y", float(y))
    try:
        setattr(controller.window, "_debug_last_modifiers", int(modifiers))
    except Exception:  # noqa: BLE001  # REASON: capture runtime fallback isolation
        _log_swallow("CAPT-005", "engine/input_runtime/capture_runtime.py pass-only blanket swallow")
        pass

    window = controller.window

    if window.editor_controller.active:
        if window.editor_controller.handle_mouse_drag(x, y, dx, dy, buttons, modifiers):
            return

    if bool(getattr(window, "show_debug", False)) and getattr(window, "command_palette_enabled", False) is True:
        return

    # Capture mode drag
    from engine.capture_mode import CaptureState  # noqa: PLC0415
    capture_state = getattr(window, "capture_state", None)
    if isinstance(capture_state, CaptureState) and bool(getattr(window, "show_debug", False)) and bool(getattr(capture_state, "enabled", False)):
        if not (int(buttons) & int(optional_arcade.arcade.MOUSE_BUTTON_LEFT)):
            return
        _handle_capture_drag(window, capture_state, x, y)
        return

    # Tile paint drag
    from engine.tile_paint_mode import TilePaintState  # noqa: PLC0415
    tile_paint_state = getattr(window, "tile_paint_state", None)
    if (
        bool(getattr(window, "show_debug", False))
        and isinstance(tile_paint_state, TilePaintState)
        and bool(getattr(tile_paint_state, "enabled", False))
        and bool(getattr(tile_paint_state, "stroke_active", False))
    ):
        if not (int(buttons) & int(getattr(tile_paint_state, "stroke_button", 0) or 0)):
            return
        _handle_tile_paint_drag(window, tile_paint_state, x, y)
        return

    # Entity select drag
    if bool(getattr(window, "show_debug", False)) and (int(buttons) & int(optional_arcade.arcade.MOUSE_BUTTON_LEFT)):
        from engine.entity_select_mode import EntitySelectState, other_authoring_modes_active  # noqa: PLC0415
        if not other_authoring_modes_active(window):
            state = getattr(window, "entity_select_state", None)
            if isinstance(state, EntitySelectState) and bool(getattr(state, "dragging", False)):
                _handle_entity_select_drag(window, state, x, y)


def _handle_capture_drag(window: Any, capture_state: Any, x: float, y: float) -> None:
    """Handle drag in capture mode."""
    sc = getattr(window, "scene_controller", None)
    instance = getattr(sc, "tilemap_instance", None) if sc is not None else None
    if instance is None:
        return
    map_w, map_h = getattr(instance, "map_size", (0, 0))
    tile_w, tile_h = getattr(instance, "tile_size", (0, 0))
    try:
        world_x, world_y = window.screen_to_world(float(x), float(y))
    except Exception:  # noqa: BLE001  # REASON: capture runtime fallback isolation
        return
    from engine.tile_paint_mode import world_to_tile  # noqa: PLC0415
    hit = world_to_tile(
        map_width=int(map_w),
        map_height=int(map_h),
        tile_width=int(tile_w),
        tile_height=int(tile_h),
        world_x=float(world_x),
        world_y=float(world_y),
    )
    if hit is None:
        return
    anchor = getattr(capture_state, "drag_anchor", None)
    if anchor is None:
        capture_state.drag_anchor = (int(hit[0]), int(hit[1]))
        anchor = capture_state.drag_anchor
    if anchor is None:
        return
    ax, ay = anchor
    from engine.capture_mode import normalize_rect  # noqa: PLC0415
    capture_state.rect = normalize_rect(int(ax), int(ay), int(hit[0]), int(hit[1]))


def _handle_tile_paint_drag(window: Any, tile_paint_state: Any, x: float, y: float) -> None:
    """Handle drag in tile paint mode."""
    sc = getattr(window, "scene_controller", None)
    instance = getattr(sc, "tilemap_instance", None) if sc is not None else None
    if instance is None:
        return
    map_w, map_h = getattr(instance, "map_size", (0, 0))
    tile_w, tile_h = getattr(instance, "tile_size", (0, 0))
    if not all(isinstance(v, int) for v in (map_w, map_h, tile_w, tile_h)):
        return
    try:
        world_x, world_y = window.screen_to_world(float(x), float(y))
    except Exception:  # noqa: BLE001  # REASON: capture runtime fallback isolation
        return
    from engine.tile_paint_mode import world_to_tile  # noqa: PLC0415
    hit = world_to_tile(
        map_width=int(map_w),
        map_height=int(map_h),
        tile_width=int(tile_w),
        tile_height=int(tile_h),
        world_x=float(world_x),
        world_y=float(world_y),
    )
    if hit is None:
        return
    tx, ty = hit
    tile_paint_state.stroke_last_hit = (int(tx), int(ty))
    if str(getattr(tile_paint_state, "stroke_tool", "") or "") == "brush":
        tile_paint_state.stroke_coords.add((int(tx), int(ty)))


def _handle_entity_select_drag(window: Any, state: Any, x: float, y: float) -> None:
    """Handle drag in entity select mode."""
    from engine.entity_select_mode import update_drag_rect  # noqa: PLC0415

    try:
        world_x, world_y = window.screen_to_world(float(x), float(y))
    except Exception:  # noqa: BLE001  # REASON: capture runtime fallback isolation
        return

    if str(getattr(state, "drag_mode", "") or "") == "marquee":
        update_drag_rect(state, world_x=float(world_x), world_y=float(world_y))
        return

    if str(getattr(state, "drag_mode", "") or "") != "move":
        return

    anchor = getattr(state, "drag_anchor_world", None)
    if not (isinstance(anchor, tuple) and len(anchor) == 2):
        return

    dx = float(world_x) - float(anchor[0])
    dy = float(world_y) - float(anchor[1])

    sc = getattr(window, "scene_controller", None)
    mover = getattr(sc, "debug_move_entity_by_id", None) if sc is not None else None
    finder = getattr(sc, "debug_find_sprite_by_entity_id", None) if sc is not None else None
    if not callable(mover):
        return

    positions = getattr(state, "drag_start_positions", None)
    if not isinstance(positions, dict):
        positions = {}
        for entity_id in list(getattr(state, "selected_ids", []) or []):
            sprite = finder(entity_id) if callable(finder) else None
            if sprite is not None:
                cx = getattr(sprite, "center_x", None)
                cy = getattr(sprite, "center_y", None)
                if cx is not None and cy is not None:
                    positions[str(entity_id)] = (float(cx), float(cy))
        state.drag_start_positions = positions

    moved_any = False
    for entity_id in list(getattr(state, "selected_ids", []) or []):
        if entity_id not in positions:
            continue
        sx, sy = positions[entity_id]
        nx = float(sx) + dx
        ny = float(sy) + dy
        if bool(getattr(window, "entity_snap_to_tile", False)):
            from engine.entity_select_mode import snap_world_to_tile_center  # noqa: PLC0415

            snapped = snap_world_to_tile_center(window, world_x=nx, world_y=ny)
            if snapped is not None:
                nx, ny = snapped
        if mover(entity_id, x=float(nx), y=float(ny)):
            moved_any = True

    if moved_any:
        if not bool(getattr(state, "drag_undo_pushed", False)):
            pusher = getattr(window, "push_undo_frame", None)
            if callable(pusher):
                pusher("entity_select_drag")
            state.drag_undo_pushed = True
        if not bool(getattr(state, "drag_dirty_marked", False)):
            marker = getattr(window, "mark_scene_dirty", None)
            if callable(marker):
                marker("entity_select_multi")
            state.drag_dirty_marked = True
