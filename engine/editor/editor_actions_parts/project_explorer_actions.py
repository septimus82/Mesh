"""Project Explorer action handlers: toggle, reveal, copy, select, context menu, rename, move."""

from __future__ import annotations

import os
from typing import Any

from engine.editor.editor_actions_parts._shared import _get_editor

__all__ = [
    "_reveal_current_in_project_explorer",
    "_copy_project_explorer_path",
    "_copy_project_explorer_common_parent",
    "_project_explorer_select_all",
    "_project_explorer_clear_selection",
    "_project_explorer_invert_selection",
    "_project_explorer_delete_selected",
    "_project_explorer_context_menu_open",
    "_project_explorer_context_menu_close",
    "_project_explorer_context_menu_move",
    "_action_project_explorer_context_menu_up",
    "_action_project_explorer_context_menu_down",
    "_project_explorer_context_menu_activate",
    "_safe_rename_selected_asset",
    "_safe_move_selected_asset",
    "_safe_move_selected_assets",
    "_enabled_safe_move_refactor",
    "_safe_move_refactor_wrapper",
    "_enabled_inline_rename_active",
    "_inline_rename_commit",
    "_inline_rename_cancel",
    "_inline_rename_backspace",
    "_inline_rename_delete",
    "_inline_rename_cursor_left",
    "_inline_rename_cursor_left_extend",
    "_inline_rename_cursor_right",
    "_inline_rename_cursor_right_extend",
    "_inline_rename_cursor_home",
    "_inline_rename_cursor_home_extend",
    "_inline_rename_cursor_end",
    "_inline_rename_cursor_end_extend",
    "_inline_rename_cursor_word_left",
    "_inline_rename_cursor_word_left_extend",
    "_inline_rename_cursor_word_right",
    "_inline_rename_cursor_word_right_extend",
    "_inline_rename_delete_prev_word",
    "_inline_rename_delete_next_word",
    "_enabled_project_explorer_file_selection",
    "_enabled_has_reveal_target",
    "_enabled_project_explorer_selection",
    "_enabled_project_explorer_active",
    "_enabled_project_explorer_context_menu_open",
]


def _reveal_current_in_project_explorer(window: Any) -> None:
    """Reveal current scene or selected entity asset in Project Explorer."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    revealer = getattr(editor, "reveal_current_in_project_explorer", None)
    if callable(revealer):
        revealer()


def _copy_project_explorer_path(window: Any) -> None:
    """Copy the selected Project Explorer row path to clipboard."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    # Direct delegation (Diet V5)
    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is None:
        return
    paths = project_ctrl.selected_paths()
    if not paths:
        return
    if hasattr(editor.file_ops, "copy_selected_paths"):
        editor.file_ops.copy_selected_paths(paths)
    else:
        editor.file_ops.copy_selected_path()


def _copy_project_explorer_common_parent(window: Any) -> None:
    """Copy common parent folder from Project Explorer selection."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is None:
        return
    paths = project_ctrl.selected_paths()
    if not paths:
        return
    copier = getattr(editor.file_ops, "copy_common_parent", None)
    if callable(copier):
        copier(paths)


def _project_explorer_select_all(window: Any) -> None:
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.select_all()


def _project_explorer_clear_selection(window: Any) -> None:
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.clear_selection()


def _project_explorer_invert_selection(window: Any) -> None:
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.invert_selection()


def _project_explorer_delete_selected(window: Any) -> None:
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    deleter = getattr(editor, "delete_selected", None)
    if callable(deleter):
        deleter()


def _project_explorer_context_menu_open(window: Any) -> None:
    editor = _get_editor(window)
    if editor is None:
        return
    opener = getattr(editor, "open_project_explorer_context_menu_at_selection", None)
    if callable(opener):
        opener()


def _project_explorer_context_menu_close(window: Any) -> None:
    editor = _get_editor(window)
    if editor is None:
        return
    project = getattr(editor, "project_explorer", None)
    if project is None:
        return
    closer = getattr(project, "close_context_menu", None)
    if callable(closer):
        closer(editor)


def _project_explorer_context_menu_move(window: Any, delta: int) -> None:
    editor = _get_editor(window)
    if editor is None:
        return
    project = getattr(editor, "project_explorer", None)
    if project is None:
        return
    mover = getattr(project, "move_context_menu_selection", None)
    if callable(mover):
        mover(delta)


def _action_project_explorer_context_menu_up(window: Any) -> None:
    _project_explorer_context_menu_move(window, -1)


def _action_project_explorer_context_menu_down(window: Any) -> None:
    _project_explorer_context_menu_move(window, 1)


def _project_explorer_context_menu_activate(window: Any) -> None:
    editor = _get_editor(window)
    if editor is None:
        return
    project = getattr(editor, "project_explorer", None)
    if project is None:
        return
    activator = getattr(project, "activate_context_menu_item", None)
    if callable(activator):
        activator(editor)


def _safe_rename_selected_asset(window: Any) -> None:
    """Initiate inline rename for selected Project Explorer asset.

    Uses the new inline rename UX via ProjectExplorerController.
    Press F2 to start editing, Enter to commit, Esc to cancel.
    """
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    # Check capability via Protocol
    if not editor.file_ops.can_safe_rename_selected_asset():
        return

    # Get selected entry path to populate UI
    path_getter = getattr(editor, "_get_selected_project_entry_path", None)
    old_path: str | None = None
    if callable(path_getter):
        result = path_getter()
        old_path = result if isinstance(result, str) else None

    if not old_path:
        return

    # Start inline rename via project explorer controller
    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.begin_inline_rename(old_path)


def _safe_move_selected_asset(window: Any) -> None:
    """Initiate safe move for selected Project Explorer asset.
    
    Prompts for destination folder (currently strictly requires UI implementation or test harness).
    
    If no UI available, this action does nothing (safe no-op).
    """
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    # Check capability via Protocol
    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is None:
        return
    selection_count = getattr(project_ctrl, "selection_count", None)
    if callable(selection_count):
        sc_result = selection_count()
        if isinstance(sc_result, (int, float)) and sc_result > 1:
            _safe_move_selected_assets(window)
            return

    if not editor.file_ops.can_safe_move_selected_asset():
        return

    prompter = getattr(editor, "prompt_project_explorer_move_destination", None)
    if callable(prompter):
        prompter(lambda dest: editor.safe_move_selected_asset(dest))
        return

    # Fallback toast if no prompt handler
    hud = getattr(window, "player_hud", None)
    toaster = getattr(hud, "enqueue_toast", None) if hud is not None else None
    if callable(toaster):
        toaster("Safe Move: Select specific folder logic pending UI", seconds=2.5)


def _safe_move_selected_assets(window: Any) -> None:
    """Initiate safe move for multiple selected Project Explorer assets."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is None:
        return

    selection_count = getattr(project_ctrl, "selection_count", None)
    if not callable(selection_count):
        return
    sc_result = selection_count()
    if not isinstance(sc_result, (int, float)) or sc_result <= 1:
        return

    prompter = getattr(editor, "prompt_project_explorer_move_destination", None)
    if callable(prompter):
        # V2 Refactor Path for multi-select
        prompter(lambda dest: editor.file_ops.request_safe_move_refactor(dest))


def _enabled_safe_move_refactor(controller: Any, window: Any) -> bool:
    """Enabled if we can move file (legacy) or folder/multi (v2)."""
    # Base check for project explorer focus/selection
    editor = _get_editor(window)
    if not editor: return False
    
    from engine.editor.project_explorer_power_tools_model import should_handle_project_explorer_shortcut  # noqa: PLC0415
    if not should_handle_project_explorer_shortcut(editor):
        return False
        
    ops = editor.file_ops
    return bool(ops.can_safe_move_selected_asset() or ops.can_safe_move_selected_assets_folder())


def _safe_move_refactor_wrapper(window: Any) -> None:
    """Dispatch to Legacy or V2 move depending on selection."""
    editor = _get_editor(window)
    if not editor: return
    
    ops = editor.file_ops
    use_v2 = ops.can_safe_move_selected_assets_folder()
    # Check multi-select too?
    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl and getattr(project_ctrl, "selection_count", lambda: 0)() > 1:
        use_v2 = True
        
    prompter = getattr(editor, "prompt_project_explorer_move_destination", None)
    if not callable(prompter): 
        # Toast fallback?
        return

    if use_v2:
        prompter(lambda dest: ops.request_safe_move_refactor(dest))
    else:
        # Legacy
        prompter(lambda dest: editor.safe_move_selected_asset(dest))

    if callable(prompter):
        prompter(lambda dest: editor.safe_move_selected_assets(dest))
        return

    hud = getattr(window, "player_hud", None)
    toaster = getattr(hud, "enqueue_toast", None) if hud is not None else None
    if callable(toaster):
        toaster("Safe Move: Select specific folder logic pending UI", seconds=2.5)


# --- Inline Rename Action Handlers ---


def _enabled_inline_rename_active(_controller: Any, window: Any) -> bool:
    """Check if inline rename is active in Project Explorer."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return False

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is None:
        return False

    return getattr(project_ctrl, "inline_rename_active", False) is True


def _inline_rename_commit(window: Any) -> None:
    """Commit the inline rename and perform the actual file rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is None:
        return

    success, new_name = project_ctrl.commit_inline_rename()
    if not success or not new_name:
        # Either no change or error - if error, state is preserved for retry
        # Show toast if there was an error
        should_commit, _, error = project_ctrl.get_inline_rename_commit_result()
        if error:
            hud = getattr(window, "player_hud", None)
            toaster = getattr(hud, "enqueue_toast", None) if hud else None
            if callable(toaster):
                toaster(f"Rename failed: {error}", seconds=2.5)
        return

    # Perform actual rename via file_ops
    file_ops = getattr(editor, "file_ops", None)
    if file_ops is not None:
        if hasattr(file_ops, "request_safe_rename_refactor"):
             file_ops.request_safe_rename_refactor(new_name)
        elif hasattr(file_ops, "rename_selected_asset"):
             file_ops.rename_selected_asset(new_name)


def _inline_rename_cancel(window: Any) -> None:
    """Cancel the inline rename operation."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.cancel_inline_rename()


def _inline_rename_backspace(window: Any) -> None:
    """Delete character before cursor in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_backspace()


def _inline_rename_delete(window: Any) -> None:
    """Delete character at cursor in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_delete()


def _inline_rename_cursor_left(window: Any) -> None:
    """Move cursor left in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_cursor_left(shift=False)


def _inline_rename_cursor_left_extend(window: Any) -> None:
    """Move cursor left and extend selection in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_cursor_left(shift=True)


def _inline_rename_cursor_right(window: Any) -> None:
    """Move cursor right in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_cursor_right(shift=False)


def _inline_rename_cursor_right_extend(window: Any) -> None:
    """Move cursor right and extend selection in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_cursor_right(shift=True)


def _inline_rename_cursor_home(window: Any) -> None:
    """Move cursor to start in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_cursor_home(shift=False)


def _inline_rename_cursor_home_extend(window: Any) -> None:
    """Move cursor to start and extend selection in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_cursor_home(shift=True)


def _inline_rename_cursor_end(window: Any) -> None:
    """Move cursor to end in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_cursor_end(shift=False)


def _inline_rename_cursor_end_extend(window: Any) -> None:
    """Move cursor to end and extend selection in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_cursor_end(shift=True)


def _inline_rename_cursor_word_left(window: Any) -> None:
    """Move cursor left by word in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_cursor_word_left(shift=False)


def _inline_rename_cursor_word_left_extend(window: Any) -> None:
    """Move cursor left by word and extend selection in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_cursor_word_left(shift=True)


def _inline_rename_cursor_word_right(window: Any) -> None:
    """Move cursor right by word in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_cursor_word_right(shift=False)


def _inline_rename_cursor_word_right_extend(window: Any) -> None:
    """Move cursor right by word and extend selection in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_cursor_word_right(shift=True)


def _inline_rename_delete_prev_word(window: Any) -> None:
    """Delete previous word in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_delete_prev_word()


def _inline_rename_delete_next_word(window: Any) -> None:
    """Delete next word in inline rename."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return

    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is not None:
        project_ctrl.handle_rename_delete_next_word()


# -------------------------------------------------------------------------
# Project Explorer Enabled Guards
# -------------------------------------------------------------------------


def _enabled_project_explorer_file_selection(_controller: Any, window: Any) -> bool:
    """Check if there's a file (not folder) selected in Project Explorer."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return False

    from engine.editor.project_explorer_power_tools_model import should_handle_project_explorer_shortcut  # noqa: PLC0415

    if not should_handle_project_explorer_shortcut(editor):
        return False

    can_rename = False
    can_move = False
    if hasattr(editor.file_ops, "can_safe_rename_selected_asset"):
        can_rename = bool(editor.file_ops.can_safe_rename_selected_asset())
    if hasattr(editor.file_ops, "can_safe_move_selected_asset"):
        can_move = bool(editor.file_ops.can_safe_move_selected_asset())
    return can_rename or can_move


def _enabled_has_reveal_target(_controller: Any, window: Any) -> bool:
    """Check if there's a valid reveal target (scene or selected entity asset)."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return False

    # Check for scene path
    sc = getattr(window, "scene_controller", None)
    if sc is not None:
        scene_path = getattr(sc, "current_scene_path", None)
        if scene_path:
            return True

    # Check for selected entity with asset
    entity_id = getattr(editor, "_primary_selected_id", None)
    if entity_id:
        return True  # Simplified - assume entity might have asset

    return False


def _enabled_project_explorer_selection(_controller: Any, window: Any) -> bool:
    """Check if there's a selection in Project Explorer."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return False

    from engine.editor.project_explorer_power_tools_model import should_handle_project_explorer_shortcut  # noqa: PLC0415

    if not should_handle_project_explorer_shortcut(editor):
        return False
    project_ctrl = getattr(editor, "project_explorer", None)
    if project_ctrl is None:
        return False
    count = getattr(project_ctrl, "selection_count", None)
    if callable(count):
        result = count()
        return bool(isinstance(result, (int, float)) and result > 0)
    state = getattr(project_ctrl, "selection_state", None)
    if state is not None:
        selected = getattr(state, "selected_indices", None)
        if selected:
            return True
    return False


def _enabled_project_explorer_active(_controller: Any, window: Any) -> bool:
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return False
    from engine.editor.project_explorer_power_tools_model import should_handle_project_explorer_shortcut  # noqa: PLC0415

    return bool(should_handle_project_explorer_shortcut(editor))


def _enabled_project_explorer_context_menu_open(_controller: Any, window: Any) -> bool:
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return False
    from engine.editor.editor_panels_query import panels_is_open  # noqa: PLC0415

    return panels_is_open(editor, "project_context_menu")
