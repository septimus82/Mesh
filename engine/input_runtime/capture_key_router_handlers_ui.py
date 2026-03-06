from __future__ import annotations

from typing import Any

from engine.input_runtime.capture_runtime_focus_model import CaptureFocusSnapshot
from engine.command_palette_controller import (
    handle_command_palette_activate,
    handle_command_palette_cancel_or_close,
    handle_command_palette_history_navigate,
    handle_command_palette_navigate,
    handle_command_palette_toggle_help,
    handle_command_palette_toggle,
)


def dispatch_ui_action(
    window: Any,
    snapshot: CaptureFocusSnapshot,
    action_id: str,
    *,
    key: int | None = None,
    modifiers: int | None = None,
) -> bool:
    if action_id.startswith("capture.confirm_modal."):
        if action_id == "capture.confirm_modal.cancel":
            return _handle_confirm_modal_cancel(window)
        if action_id == "capture.confirm_modal.confirm":
            return _handle_confirm_modal_confirm(window)
        if action_id == "capture.confirm_modal.deny":
            return _handle_confirm_modal_deny(window)
        return _handle_confirm_modal_scroll(window, action_id)

    if action_id.startswith("capture.context_menu."):
        if action_id == "capture.context_menu.close":
            return _handle_context_menu_close(window)
        if action_id == "capture.context_menu.up":
            return _handle_context_menu_navigate(window, -1)
        if action_id == "capture.context_menu.down":
            return _handle_context_menu_navigate(window, 1)
        if action_id == "capture.context_menu.activate":
            return _handle_context_menu_activate(window)
        return False

    if action_id.startswith("capture.keybinds."):
        if action_id == "capture.keybinds.close_or_cancel":
            return _handle_keybinds_close_or_cancel(window)
        if action_id == "capture.keybinds.up":
            return _handle_keybinds_navigate(window, -1)
        if action_id == "capture.keybinds.down":
            return _handle_keybinds_navigate(window, 1)
        if action_id == "capture.keybinds.record_or_apply":
            return _handle_keybinds_record_or_apply(window)
        if action_id == "capture.keybinds.unbind":
            return _handle_keybinds_unbind(window)
        return False

    if action_id.startswith("capture.inline_rename."):
        if action_id == "capture.inline_rename.cancel":
            return _handle_inline_rename_cancel(window)
        if action_id == "capture.inline_rename.confirm":
            return _handle_inline_rename_confirm(window)
        return False

    if action_id.startswith("capture.command_palette."):
        if action_id == "capture.command_palette.cancel_or_close":
            return handle_command_palette_cancel_or_close(window)
        if action_id == "capture.command_palette.up":
            return handle_command_palette_navigate(window, -1)
        if action_id == "capture.command_palette.down":
            return handle_command_palette_navigate(window, 1)
        if action_id == "capture.command_palette.history_prev":
            return handle_command_palette_history_navigate(window, -1)
        if action_id == "capture.command_palette.history_next":
            return handle_command_palette_history_navigate(window, 1)
        if action_id == "capture.command_palette.activate":
            return handle_command_palette_activate(window, snapshot, repeat=False)
        if action_id == "capture.command_palette.activate_repeat":
            return handle_command_palette_activate(window, snapshot, repeat=True)
        if action_id == "capture.command_palette.toggle":
            return handle_command_palette_toggle(window)
        if action_id == "capture.command_palette.help_toggle":
            return handle_command_palette_toggle_help(window)
        return False

    if action_id.startswith("capture.console."):
        if action_id == "capture.console.toggle":
            return _handle_console_toggle(window)
        if action_id == "capture.console.close":
            return _handle_console_close(window)
        return False

    if action_id.startswith("capture.project_explorer."):
        return _handle_project_explorer_action(window, action_id)

    if action_id.startswith("capture.problems."):
        return _handle_problems_action(window, action_id)

    return False


# CONFIRM MODAL handlers

def _handle_confirm_modal_cancel(window: Any) -> bool:
    editor = getattr(window, "editor_controller", None)
    confirm = getattr(editor, "confirm_modal", None) if editor else None
    if confirm is None:
        return False
    cancel = getattr(confirm, "cancel", None)
    if callable(cancel):
        cancel()
        return True
    return False


def _handle_confirm_modal_confirm(window: Any) -> bool:
    editor = getattr(window, "editor_controller", None)
    confirm = getattr(editor, "confirm_modal", None) if editor else None
    if confirm is None:
        return False
    do_confirm = getattr(confirm, "confirm", None)
    if callable(do_confirm):
        do_confirm()
        return True
    return False


def _handle_confirm_modal_deny(window: Any) -> bool:
    editor = getattr(window, "editor_controller", None)
    confirm = getattr(editor, "confirm_modal", None) if editor else None
    if confirm is None:
        return False
    deny = getattr(confirm, "deny", None)
    if callable(deny):
        deny()
        return True
    return False


def _handle_confirm_modal_scroll(window: Any, action_id: str) -> bool:
    editor = getattr(window, "editor_controller", None)
    confirm = getattr(editor, "confirm_modal", None) if editor else None
    if confirm is None:
        return False

    if action_id == "capture.confirm_modal.scroll_up":
        fn = getattr(confirm, "scroll_up", None)
    elif action_id == "capture.confirm_modal.scroll_down":
        fn = getattr(confirm, "scroll_down", None)
    elif action_id == "capture.confirm_modal.page_up":
        fn = getattr(confirm, "page_up", None)
    elif action_id == "capture.confirm_modal.page_down":
        fn = getattr(confirm, "page_down", None)
    elif action_id == "capture.confirm_modal.scroll_top":
        fn = getattr(confirm, "scroll_to_top", None)
    elif action_id == "capture.confirm_modal.scroll_bottom":
        fn = getattr(confirm, "scroll_to_bottom", None)
    else:
        return False

    if callable(fn):
        fn()
        return True
    return True


# CONTEXT MENU handlers

def _handle_context_menu_close(window: Any) -> bool:
    editor = getattr(window, "editor_controller", None)
    project = getattr(editor, "project_explorer", None) if editor else None
    if project is None:
        return False
    closer = getattr(project, "close_context_menu", None)
    if callable(closer):
        closer()
        return True
    return False


def _handle_context_menu_navigate(window: Any, direction: int) -> bool:
    editor = getattr(window, "editor_controller", None)
    project = getattr(editor, "project_explorer", None) if editor else None
    if project is None:
        return False
    nav = getattr(project, "navigate_context_menu", None)
    if callable(nav):
        nav(direction)
        return True
    return False


def _handle_context_menu_activate(window: Any) -> bool:
    editor = getattr(window, "editor_controller", None)
    project = getattr(editor, "project_explorer", None) if editor else None
    if project is None:
        return False
    activate = getattr(project, "activate_context_menu", None)
    if callable(activate):
        return bool(activate())
    return False


# KEYBINDS handlers

def _handle_keybinds_close_or_cancel(window: Any) -> bool:
    editor = getattr(window, "editor_controller", None)
    keybinds = getattr(editor, "keybinds", None) if editor else None
    if keybinds is None:
        return False
    cancel = getattr(keybinds, "cancel_recording", None)
    if callable(cancel) and cancel():
        return True
    close = getattr(keybinds, "close", None)
    if callable(close):
        close()
        return True
    return True


def _handle_keybinds_navigate(window: Any, direction: int) -> bool:
    editor = getattr(window, "editor_controller", None)
    keybinds = getattr(editor, "keybinds", None) if editor else None
    if keybinds is None:
        return False
    nav = getattr(keybinds, "navigate", None)
    if callable(nav):
        nav(direction)
        return True
    return True


def _handle_keybinds_record_or_apply(window: Any) -> bool:
    editor = getattr(window, "editor_controller", None)
    keybinds = getattr(editor, "keybinds", None) if editor else None
    if keybinds is None:
        return False
    apply_fn = getattr(keybinds, "apply", None)
    if callable(apply_fn):
        apply_fn()
        return True
    start = getattr(keybinds, "start_recording", None)
    if callable(start):
        start()
        return True
    return True


def _handle_keybinds_unbind(window: Any) -> bool:
    editor = getattr(window, "editor_controller", None)
    keybinds = getattr(editor, "keybinds", None) if editor else None
    if keybinds is None:
        return False
    unbind = getattr(keybinds, "unbind_selected", None)
    if callable(unbind):
        unbind()
        return True
    return True


# INLINE RENAME handlers

def _handle_inline_rename_cancel(window: Any) -> bool:
    editor = getattr(window, "editor_controller", None)
    project = getattr(editor, "project_explorer", None) if editor else None
    if project is None:
        return False
    cancel = getattr(project, "cancel_inline_rename", None)
    if callable(cancel):
        cancel()
        return True
    return False


def _handle_inline_rename_confirm(window: Any) -> bool:
    editor = getattr(window, "editor_controller", None)
    project = getattr(editor, "project_explorer", None) if editor else None
    if project is None:
        return False
    confirm = getattr(project, "confirm_inline_rename", None)
    if callable(confirm):
        confirm()
        return True
    return False


# CONSOLE handlers

def _handle_console_toggle(window: Any) -> bool:
    if getattr(window, "command_palette_enabled", False) is True:
        window.command_palette_enabled = False
        window.command_palette_prompt_active = False
    window.console_controller.toggle()
    return True


def _handle_console_close(window: Any) -> bool:
    console = getattr(window, "console_controller", None)
    if console:
        console.active = False
    return True


# PROJECT EXPLORER handlers

def _handle_project_explorer_action(window: Any, action_id: str) -> bool:
    editor = getattr(window, "editor_controller", None)
    project = getattr(editor, "project_explorer", None) if editor else None
    if project is None:
        return False

    action_map = {
        "capture.project_explorer.up": ("navigate", -1),
        "capture.project_explorer.down": ("navigate", 1),
        "capture.project_explorer.collapse": ("collapse_selected", None),
        "capture.project_explorer.expand": ("expand_selected", None),
        "capture.project_explorer.open": ("open_selected", None),
        "capture.project_explorer.rename": ("start_inline_rename", None),
        "capture.project_explorer.delete": ("delete_selected", None),
        "capture.project_explorer.home": ("navigate_to_first", None),
        "capture.project_explorer.end": ("navigate_to_last", None),
        "capture.project_explorer.page_up": ("page_up", None),
        "capture.project_explorer.page_down": ("page_down", None),
        "capture.project_explorer.context_menu": ("open_context_menu_for_selected", None),
    }

    method_name, arg = action_map.get(action_id, ("", None))
    method = getattr(project, method_name, None) if method_name else None
    if callable(method):
        if arg is None:
            method()
        else:
            method(arg)
        return True
    return False


# PROBLEMS handlers

def _handle_problems_action(window: Any, action_id: str) -> bool:
    editor = getattr(window, "editor_controller", None)
    problems = getattr(editor, "problems", None) if editor else None
    if problems is None:
        return False

    if action_id == "capture.problems.up":
        nav = getattr(problems, "navigate", None)
        if callable(nav):
            nav(-1)
        return True
    if action_id == "capture.problems.down":
        nav = getattr(problems, "navigate", None)
        if callable(nav):
            nav(1)
        return True
    if action_id == "capture.problems.jump":
        jump = getattr(problems, "jump_to_selected", None)
        if callable(jump):
            jump()
        return True
    if action_id == "capture.problems.copy_location":
        copy_loc = getattr(problems, "copy_selected_location", None)
        if callable(copy_loc):
            copy_loc()
        return True

    return False


__all__ = ["dispatch_ui_action"]
