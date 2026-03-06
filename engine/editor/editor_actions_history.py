"""History/undo/redo related editor actions."""

from __future__ import annotations

from typing import Any, Callable

GetEditorFn = Callable[[Any], Any | None]


def _enabled_can_undo(controller: Any, _window: Any) -> bool:
    undo_ctrl = getattr(controller, "undo", None)
    if undo_ctrl is not None:
        from engine.editor.editor_undo_controller import EditorUndoController  # noqa: PLC0415

        if isinstance(undo_ctrl, EditorUndoController):
            return bool(undo_ctrl.can_undo())
    return False


def _enabled_can_redo(controller: Any, _window: Any) -> bool:
    undo_ctrl = getattr(controller, "undo", None)
    if undo_ctrl is not None:
        from engine.editor.editor_undo_controller import EditorUndoController  # noqa: PLC0415

        if isinstance(undo_ctrl, EditorUndoController):
            return bool(undo_ctrl.can_redo())
    return False


def _undo(window: Any, get_editor: GetEditorFn) -> None:
    editor = get_editor(window)
    undo_ctrl = getattr(editor, "undo", None) if editor is not None else None
    if undo_ctrl is not None and hasattr(undo_ctrl, "undo"):
        undo_ctrl.undo()
        return
    undoer = getattr(editor, "undo_last", None) if editor is not None else None
    if callable(undoer):
        undoer()


def _redo(window: Any, get_editor: GetEditorFn) -> None:
    editor = get_editor(window)
    undo_ctrl = getattr(editor, "undo", None) if editor is not None else None
    if undo_ctrl is not None and hasattr(undo_ctrl, "redo"):
        undo_ctrl.redo()
        return
    redoer = getattr(editor, "redo_last", None) if editor is not None else None
    if callable(redoer):
        redoer()
