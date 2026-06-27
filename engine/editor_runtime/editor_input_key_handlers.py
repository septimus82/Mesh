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

    if _handle_ai_chat_key(controller, key, modifiers):
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

    from engine.editor_runtime.editor_database_form_input import (  # noqa: PLC0415
        active_database_form,
        dispatch_database_form_key,
    )

    if key == optional_arcade.arcade.key.TAB and active_database_form(controller) is None:
        if not _has_text_input_focus_or_edit_mode(controller):
            return _cycle_right_dock_tab(controller, -1 if (modifiers & optional_arcade.arcade.key.MOD_SHIFT) else 1)

    if dispatch_database_form_key(controller, key, modifiers):
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
    from engine.editor_runtime.editor_database_form_input import _form_should_route  # noqa: PLC0415

    return _form_should_route(controller, item_editor, "Items")


def _prefab_editor_should_route(controller: EditorController, prefab_editor: object) -> bool:
    from engine.editor_runtime.editor_database_form_input import _form_should_route  # noqa: PLC0415

    return _form_should_route(controller, prefab_editor, "Prefabs")


def _has_text_input_focus_or_edit_mode(controller: EditorController) -> bool:
    if _ai_chat_input_focused(controller):
        return True
    if bool(getattr(controller, "_inspector_text_edit_active", False)):
        return True
    if bool(getattr(controller, "entity_panels_text_edit_active", False)):
        return True
    if bool(getattr(controller, "dialogue_panel_active", False)) and bool(getattr(controller, "dialogue_editing", False)):
        return True
    if bool(getattr(controller, "animation_active", False)) and bool(getattr(controller, "animation_editing", False)):
        return True
    search = getattr(controller, "search", None)
    if search is not None and getattr(search, "is_search_focused", lambda: False)():
        return True
    return False


def _handle_ai_chat_key(controller: EditorController, key: int, modifiers: int) -> bool:
    dock_ctl = getattr(controller, "dock", None)
    snapshot = dock_ctl.get_snapshot() if dock_ctl is not None and hasattr(dock_ctl, "get_snapshot") else dock_ctl
    if (getattr(snapshot, "right_tab", "Inspector") or "Inspector") != "AI Chat":
        return False
    overlay = getattr(getattr(controller, "window", None), "ai_chat_overlay", None)
    handler = getattr(overlay, "handle_key", None) if overlay is not None else None
    return bool(callable(handler) and handler(key, modifiers))


def _ai_chat_input_focused(controller: EditorController) -> bool:
    dock_ctl = getattr(controller, "dock", None)
    snapshot = dock_ctl.get_snapshot() if dock_ctl is not None and hasattr(dock_ctl, "get_snapshot") else dock_ctl
    if (getattr(snapshot, "right_tab", "Inspector") or "Inspector") != "AI Chat":
        return False
    chat = getattr(controller, "chat", None)
    return bool(getattr(chat, "input_focused", False))


def _cycle_right_dock_tab(controller: EditorController, delta: int) -> bool:
    from engine.editor.dock_tab_registry import RIGHT_DOCK_TABS  # noqa: PLC0415

    tabs = tuple(RIGHT_DOCK_TABS)
    if not tabs:
        return False

    dock = getattr(controller, "dock", None)
    snapshot = dock.get_snapshot() if dock is not None and hasattr(dock, "get_snapshot") else dock
    current = getattr(snapshot, "right_tab", "Inspector") or "Inspector"
    try:
        index = tabs.index(str(current))
    except ValueError:
        index = 0
    next_tab = tabs[(index + int(delta)) % len(tabs)]

    inspector = getattr(controller, "inspector", None)
    toggle_inspector = getattr(inspector, "toggle_inspector_focus", None) if inspector is not None else None
    if callable(toggle_inspector) and getattr(controller, "selected_entity", None) is not None:
        toggle_inspector()

    apply_tab_change = getattr(dock, "apply_tab_change", None) if dock is not None else None
    if callable(apply_tab_change):
        apply_tab_change(controller, "right", next_tab)
        return True
    setter = getattr(dock, "set_right_tab", None) if dock is not None else None
    if callable(setter):
        setter(next_tab, force=True)
        return True
    return False
