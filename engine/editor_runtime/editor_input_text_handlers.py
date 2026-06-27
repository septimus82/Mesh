from __future__ import annotations

from typing import TYPE_CHECKING

from engine.editor.editor_modal_state_query import is_scene_browser_active

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController as EditorController


def handle_text_input(controller: EditorController, text: str) -> None:
    if not controller.active:
        return

    from engine.editor.editor_panels_query import panels_is_open  # noqa: PLC0415

    if panels_is_open(controller, "unsaved_confirm"):
        return

    if _handle_ai_chat_text(controller, text):
        return

    # Project Explorer inline rename text input
    project_ctrl = getattr(controller, "project_explorer", None)
    if project_ctrl is not None and getattr(project_ctrl, "inline_rename_active", False):
        handler = getattr(project_ctrl, "handle_rename_text_input", None)
        if callable(handler) and handler(text):
            return

    search = getattr(controller, "search", None)
    if search is not None and search.is_search_focused():
        search.append_search_text(text)
        return

    if getattr(controller, "_find_everything_open", False):
        appender = getattr(controller, "append_find_query_text", None)
        if callable(appender):
            appender(text)
        return

    if getattr(controller, "asset_browser_active", False):
        asset_browser = getattr(controller, "asset_browser", None)
        handler = getattr(asset_browser, "handle_asset_browser_text_input", None) if asset_browser is not None else None
        if callable(handler) and handler(text):
            return

    from engine.editor_runtime.editor_database_form_input import dispatch_database_form_text  # noqa: PLC0415

    if dispatch_database_form_text(controller, text):
        return

    if is_scene_browser_active(controller):
        handler = getattr(controller, "_handle_scene_browser_text_input", None)
        if callable(handler) and handler(text):
            return

    if getattr(controller, "scene_switcher_active", False):
        handler = getattr(controller, "_handle_scene_switcher_text_input", None)
        if callable(handler) and handler(text):
            return

    if panels_is_open(controller, "command_palette"):
        search = getattr(controller, "search", None)
        if search is not None:
            handler = getattr(search, "append_command_palette_text", None)
            if callable(handler):
                handler(text)
        return

    if controller.entity_panels_active:
        handler = getattr(controller, "_handle_entity_panels_text_input", None)
        if callable(handler) and handler(text):
            return

    # Component Inspector text input (when in text edit mode)
    if getattr(controller, "_inspector_text_edit_active", False):
        inspector_text_handler = getattr(controller, "_handle_inspector_text_input", None)
        if callable(inspector_text_handler) and inspector_text_handler(text):
            return

    if controller.dialogue_panel_active and controller.dialogue_editing:
        if text and text.isprintable():
            controller.dialogue_edit_buffer += text
        return

    if controller.animation_active and controller.animation_editing:
        if text and text.isprintable():
            controller.animation_edit_buffer += text
        return

    if controller.palette_active and controller.palette_filter_active:
        if text.isprintable():
            controller.palette_filter += text
            controller._refresh_palette_list()
            prewarm = getattr(controller, "_prewarm_visible_palette_thumbs", None)
            if callable(prewarm):
                prewarm()
        return

    if not controller.hierarchy_active:
        return

    if controller.hierarchy_rename_active:
        if text not in ("\r", "\n") and text.isprintable():
            controller.hierarchy_rename_buffer += text
        return

    if controller.hierarchy_filter_active:
        # Filter out control chars if any leak through
        if text.isprintable():
            controller.hierarchy_filter += text
            controller._refresh_hierarchy_list()


def _handle_ai_chat_text(controller: EditorController, text: str) -> bool:
    dock_ctl = getattr(controller, "dock", None)
    snapshot = dock_ctl.get_snapshot() if dock_ctl is not None and hasattr(dock_ctl, "get_snapshot") else dock_ctl
    if (getattr(snapshot, "right_tab", "Inspector") or "Inspector") != "AI Chat":
        return False
    overlay = getattr(getattr(controller, "window", None), "ai_chat_overlay", None)
    handler = getattr(overlay, "on_text", None) if overlay is not None else None
    return bool(callable(handler) and handler(text))


def _item_editor_should_route(controller: EditorController, item_editor: object) -> bool:
    from engine.editor_runtime.editor_database_form_input import _form_should_route  # noqa: PLC0415

    return _form_should_route(controller, item_editor, "Items")


def _prefab_editor_should_route(controller: EditorController, prefab_editor: object) -> bool:
    from engine.editor_runtime.editor_database_form_input import _form_should_route  # noqa: PLC0415

    return _form_should_route(controller, prefab_editor, "Prefabs")
