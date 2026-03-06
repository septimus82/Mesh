"""Selection-focused editor actions extracted from editor_actions."""

from __future__ import annotations

from typing import Any, Callable

GetEditorFn = Callable[[Any], Any | None]


def _action_align_left(window: Any, get_editor: GetEditorFn) -> None:
    editor = get_editor(window)
    if editor is not None:
        align = getattr(editor, "align", None)
        if align is not None:
            align.align_left()


def _action_align_right(window: Any, get_editor: GetEditorFn) -> None:
    editor = get_editor(window)
    if editor is not None:
        align = getattr(editor, "align", None)
        if align is not None:
            align.align_right()


def _action_align_top(window: Any, get_editor: GetEditorFn) -> None:
    editor = get_editor(window)
    if editor is not None:
        align = getattr(editor, "align", None)
        if align is not None:
            align.align_top()


def _action_align_bottom(window: Any, get_editor: GetEditorFn) -> None:
    editor = get_editor(window)
    if editor is not None:
        align = getattr(editor, "align", None)
        if align is not None:
            align.align_bottom()


def _action_align_center_horizontal(window: Any, get_editor: GetEditorFn) -> None:
    editor = get_editor(window)
    if editor is not None:
        align = getattr(editor, "align", None)
        if align is not None:
            align.align_center_horizontal()


def _action_align_center_vertical(window: Any, get_editor: GetEditorFn) -> None:
    editor = get_editor(window)
    if editor is not None:
        align = getattr(editor, "align", None)
        if align is not None:
            align.align_center_vertical()


def _action_distribute_horizontal(window: Any, get_editor: GetEditorFn) -> None:
    editor = get_editor(window)
    if editor is not None:
        align = getattr(editor, "align", None)
        if align is not None:
            align.distribute_horizontal()


def _action_distribute_vertical(window: Any, get_editor: GetEditorFn) -> None:
    editor = get_editor(window)
    if editor is not None:
        align = getattr(editor, "align", None)
        if align is not None:
            align.distribute_vertical()


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
