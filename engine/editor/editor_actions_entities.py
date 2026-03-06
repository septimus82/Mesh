"""Entity lifecycle / prefab-related editor actions."""

from __future__ import annotations

from typing import Any, Callable

GetEditorFn = Callable[[Any], Any | None]


def _toggle_entity_panels(window: Any, get_editor: GetEditorFn) -> None:
    editor = get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return
    toggler = getattr(editor, "toggle_entity_panels", None)
    if callable(toggler):
        toggler()


def _toggle_prefab_palette(window: Any, get_editor: GetEditorFn) -> None:
    editor = get_editor(window)
    toggler = getattr(editor, "toggle_palette", None) if editor is not None else None
    if callable(toggler):
        toggler()


def _duplicate(window: Any, get_editor: GetEditorFn) -> None:
    editor = get_editor(window)
    duplicator = getattr(editor, "duplicate_selected", None) if editor is not None else None
    if callable(duplicator):
        duplicator()


def _delete(window: Any, get_editor: GetEditorFn) -> None:
    editor = get_editor(window)
    deleter = getattr(editor, "delete_selected", None) if editor is not None else None
    if callable(deleter):
        deleter()
