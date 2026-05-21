from __future__ import annotations

from typing import TYPE_CHECKING

import engine.optional_arcade as optional_arcade

from engine.editor.editor_panels_query import panels_is_open

from .editor_input_menu_handlers import handle_context_menu_key, handle_menu_bar_key

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController as EditorController


def handle_pre_routed_keys(controller: EditorController, key: int, modifiers: int) -> bool:
    """Handle editor key input before router/shortcuts.

    Returns True if consumed.
    """
    # UI Layer Stack Dispatch (V1)
    panels = getattr(controller, "panels", None)
    if panels is not None and panels.dispatch_input(key, modifiers):
        return True

    # Alt-drag duplicate cancel on Escape (check early)
    if key == optional_arcade.arcade.key.ESCAPE and getattr(controller, "_alt_dup_active", False):
        controller.cancel_alt_drag_duplicate()
        return True

    # Marquee cancel on Escape (check early)
    if key == optional_arcade.arcade.key.ESCAPE and getattr(controller, "_marquee_active", False):
        controller.cancel_marquee()
        return True

    if panels_is_open(controller, "unsaved_confirm"):
        handler = getattr(controller, "_handle_unsaved_confirm_input", None)
        if callable(handler):
            return bool(handler(key, modifiers))
        return True

    if key == optional_arcade.arcade.key.F and (modifiers & optional_arcade.arcade.key.MOD_CTRL):
        search = getattr(controller, "search", None)
        if search is not None and search.focus_search_for_active_panel():
            return True

    if getattr(controller, "_find_everything_open", False) and key == optional_arcade.arcade.key.TAB:
        handler = getattr(controller, "_handle_find_everything_input", None)
        if callable(handler) and handler(key, modifiers):
            return True
        return True

    search = getattr(controller, "search", None)
    if search is not None and search.is_search_focused():
        if key == optional_arcade.arcade.key.ESCAPE:
            if search.clear_search_for_active_panel():
                return True
            search.clear_search_focus()
            return True
        if key == optional_arcade.arcade.key.BACKSPACE:
            search.backspace_search_text()
            return True
        if key == optional_arcade.arcade.key.TAB:
            panel = search.get_search_focus()
            if panel == "debug":
                debug_panels = getattr(controller, "debug_panels", None)
                if debug_panels is not None:
                    delta = -1 if (modifiers & optional_arcade.arcade.key.MOD_SHIFT) else 1
                    debug_panels.advance_active_filter(delta)
                return True
        if key in (optional_arcade.arcade.key.ENTER, optional_arcade.arcade.key.RETURN):
            panel = search.get_search_focus()
            if panel == "problems":
                handler = getattr(controller, "_handle_problems_input", None)
                if callable(handler):
                    handler(key, modifiers)
            return True
        if key in (
            optional_arcade.arcade.key.UP,
            optional_arcade.arcade.key.DOWN,
            optional_arcade.arcade.key.PAGE_UP,
            optional_arcade.arcade.key.PAGE_DOWN,
        ):
            panel = search.get_search_focus()
            handler = None
            if panel == "outliner":
                handler = getattr(controller, "_handle_entity_panels_input", None)
            elif panel == "assets":
                handler = getattr(controller, "_handle_asset_browser_input", None)
            elif panel == "history":
                handler = getattr(controller, "_handle_history_input", None)
            elif panel == "problems":
                handler = getattr(controller, "_handle_problems_input", None)
            if callable(handler):
                handler(key, modifiers)
            return True
        return True

    if getattr(controller, "_find_everything_open", False):
        handler = getattr(controller, "_handle_find_everything_input", None)
        if callable(handler) and handler(key, modifiers):
            return True
        return True

    item_editor = getattr(controller, "item_editor", None)
    if item_editor is not None and _item_editor_should_route(controller, item_editor):
        handler = getattr(item_editor, "handle_item_editor_key", None)
        if callable(handler):
            return bool(handler(key, modifiers))
        return True

    # Menu bar handles Escape to close
    if handle_menu_bar_key(controller, key, modifiers):
        return True

    # Context menu handles Escape to close
    if handle_context_menu_key(controller, key, modifiers):
        return True

    if getattr(controller, "asset_place_active", False):
        if key == optional_arcade.arcade.key.ESCAPE:
            controller.asset_place_active = False
            return True
        if key == optional_arcade.arcade.key.ENTER:
            mx = getattr(controller.window, "_mouse_x", 0)
            my = getattr(controller.window, "_mouse_y", 0)
            wx, wy = controller.window.screen_to_world(mx, my)
            if hasattr(controller, "place_asset_at"):
                controller.place_asset_at(wx, wy)
            return True

    return False


def _item_editor_should_route(controller: EditorController, item_editor: object) -> bool:
    is_active = getattr(item_editor, "is_edit_mode_active", None)
    if not callable(is_active) or not bool(is_active()):
        return False
    dock = getattr(controller, "dock", None)
    snapshot = dock.get_snapshot() if dock is not None and hasattr(dock, "get_snapshot") else dock
    return (getattr(snapshot, "right_tab", "Inspector") or "Inspector") == "Items"
