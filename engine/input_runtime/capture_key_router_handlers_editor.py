from __future__ import annotations

from typing import Any


def dispatch_editor_action(window: Any, action_id: str) -> bool:
    if action_id == "capture.editor.undo":
        return _handle_editor_undo(window)
    if action_id == "capture.editor.redo":
        return _handle_editor_redo(window)
    return False


def _handle_editor_undo(window: Any) -> bool:
    editor = getattr(window, "editor_controller", None)
    if not (editor and getattr(editor, "active", False)):
        return False
    undo_ctrl = getattr(editor, "undo", None)
    if undo_ctrl is not None and hasattr(undo_ctrl, "undo"):
        undo_ctrl.undo()
        return True
    undo = getattr(editor, "undo_last", None)
    if callable(undo):
        undo()
        return True
    return False


def _handle_editor_redo(window: Any) -> bool:
    editor = getattr(window, "editor_controller", None)
    if not (editor and getattr(editor, "active", False)):
        return False
    undo_ctrl = getattr(editor, "undo", None)
    if undo_ctrl is not None and hasattr(undo_ctrl, "redo"):
        undo_ctrl.redo()
        return True
    redo = getattr(editor, "redo_last", None)
    if callable(redo):
        redo()
        return True
    return False


__all__ = ["dispatch_editor_action"]
