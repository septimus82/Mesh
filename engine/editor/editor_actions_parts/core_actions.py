"""Core action handlers: save, play, stop, undo, redo, duplicate, delete, export, quit, refactor."""

from __future__ import annotations

import os
from typing import Any

from engine.editor import editor_actions_entities as _entity_actions
from engine.editor import editor_actions_history as _history_actions
from engine.editor.editor_actions_parts._shared import _get_editor, _is_web_runtime

__all__ = [
    "_save_scene",
    "_play_from_here",
    "_stop_playing",
    "_build_windows",
    "_undo",
    "_redo",
    "_duplicate",
    "_delete",
    "_export_web_demo",
    "_quit_app",
    "_action_refactor_delete_selected",
    "_action_refactor_move_selected",
    "_action_refactor_rename_commit",
]


def _save_scene(window: Any) -> None:
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    saver = getattr(editor, "save_current_scene", None)
    if callable(saver):
        saver()


def _play_from_here(window: Any) -> None:
    editor = _get_editor(window)
    starter = getattr(editor, "play_from_here", None) if editor is not None else None
    if callable(starter):
        starter()


def _stop_playing(window: Any) -> None:
    editor = _get_editor(window)
    stopper = getattr(editor, "stop_playing", None) if editor is not None else None
    if callable(stopper):
        stopper()


def _build_windows(window: Any) -> None:
    editor = _get_editor(window)
    build = getattr(editor, "build", None) if editor is not None else None
    starter = getattr(build, "build_windows", None) if build is not None else None
    if callable(starter):
        starter()


def _undo(window: Any) -> None:
    _history_actions._undo(window, _get_editor)


def _redo(window: Any) -> None:
    _history_actions._redo(window, _get_editor)


def _duplicate(window: Any) -> None:
    _entity_actions._duplicate(window, _get_editor)


def _delete(window: Any) -> None:
    _entity_actions._delete(window, _get_editor)


def _export_web_demo(window: Any) -> None:
    if _is_web_runtime():
        return
    exporter = getattr(window, "export_web_demo", None) if window is not None else None
    if callable(exporter):
        exporter()


def _quit_app(window: Any) -> None:
    if _is_web_runtime():
        return
    closer = getattr(window, "close", None) if window is not None else None
    if callable(closer):
        closer()


def _action_refactor_delete_selected(window: Any) -> None:
    editor = _get_editor(window)
    project = getattr(editor, "project_explorer", None)
    file_ops = getattr(editor, "file_ops", None)

    if project and file_ops and hasattr(file_ops, "request_safe_delete_refactor"):
        if hasattr(project, "ensure_rows"):
            project.ensure_rows()
        paths = project.selected_paths(getattr(project, "selectable_rows", []))
        if paths:
            file_ops.request_safe_delete_refactor(paths)


def _action_refactor_move_selected(window: Any) -> None:
    editor = _get_editor(window)
    project = getattr(editor, "project_explorer", None)
    file_ops = getattr(editor, "file_ops", None)

    if project and file_ops and hasattr(file_ops, "request_safe_move_refactor"):
        # Ensure V2 capability check?
        can_move = getattr(file_ops, "can_safe_move_selected_assets_folder", lambda: True)()
        if not can_move:
             return

        prompter = getattr(editor, "prompt_project_explorer_move_destination", None)
        if callable(prompter):
            prompter(lambda dest: file_ops.request_safe_move_refactor(dest))
        else:
            file_ops.request_safe_move_refactor("")


def _action_refactor_rename_commit(window: Any) -> None:
    editor = _get_editor(window)
    project = getattr(editor, "project_explorer", None)
    if project is None or not getattr(project, "inline_rename_active", False):
        return

    should_commit, new_name, error = project.get_inline_rename_commit_result()

    if should_commit and new_name:
        state = getattr(project, "inline_rename_state", None)
        original_path = getattr(state, "original_path", "")

        parent = os.path.dirname(original_path)
        new_path = os.path.join(parent, new_name).replace("\\", "/")

        project.cancel_inline_rename()

        file_ops = getattr(editor, "file_ops", None)
        if file_ops and hasattr(file_ops, "request_safe_rename_refactor"):
            file_ops.request_safe_rename_refactor(original_path, new_path)

    elif error is None:
        project.cancel_inline_rename()
    else:
        message = f"Rename failed: {error}"
        feedback = getattr(editor, "feedback", None) if editor is not None else None
        if feedback is not None:
            feedback.error(message, ttl=2.5)
        hud = getattr(window, "player_hud", None)
        if hud:
            toaster = getattr(hud, "enqueue_" "toast", None)
            if callable(toaster):
                toaster(message, seconds=2.5)
