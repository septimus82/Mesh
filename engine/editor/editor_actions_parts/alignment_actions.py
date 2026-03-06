"""Align / Distribute action handlers."""

from __future__ import annotations

from typing import Any

from engine.editor import editor_actions_selection as _selection_actions
from engine.editor.editor_actions_parts._shared import _get_editor

__all__ = [
    "_action_align_left",
    "_action_align_right",
    "_action_align_top",
    "_action_align_bottom",
    "_action_align_center_horizontal",
    "_action_align_center_vertical",
    "_action_distribute_horizontal",
    "_action_distribute_vertical",
]


def _action_align_left(window: Any) -> None:
    _selection_actions._action_align_left(window, _get_editor)


def _action_align_right(window: Any) -> None:
    _selection_actions._action_align_right(window, _get_editor)


def _action_align_top(window: Any) -> None:
    _selection_actions._action_align_top(window, _get_editor)


def _action_align_bottom(window: Any) -> None:
    _selection_actions._action_align_bottom(window, _get_editor)


def _action_align_center_horizontal(window: Any) -> None:
    _selection_actions._action_align_center_horizontal(window, _get_editor)


def _action_align_center_vertical(window: Any) -> None:
    _selection_actions._action_align_center_vertical(window, _get_editor)


def _action_distribute_horizontal(window: Any) -> None:
    _selection_actions._action_distribute_horizontal(window, _get_editor)


def _action_distribute_vertical(window: Any) -> None:
    _selection_actions._action_distribute_vertical(window, _get_editor)
