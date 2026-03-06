"""Shared helpers and enabled-guard functions used across action buckets."""

from __future__ import annotations

import os
import sys
from typing import Any

from engine.editor import editor_actions_history as _history_actions
from engine.editor.editor_dock_query import get_dock_snapshot

__all__ = [
    "SHORTCUT_SCOPE_GLOBAL",
    "SHORTCUT_SCOPE_INLINE_RENAME",
    "SHORTCUT_SCOPE_PROJECT_EXPLORER",
    "SHORTCUT_SCOPE_PROJECT_EXPLORER_CONTEXT_MENU",
    "_is_web_runtime",
    "_get_editor",
    "_enabled_always",
    "_enabled_has_selection",
    "_enabled_has_selection_or_project_explorer",
    "_enabled_can_undo",
    "_enabled_can_redo",
    "_enabled_scene_dirty",
    "_enabled_not_web",
    "_enabled_multiselect",
    "_enabled_multiselect_3",
    "_enabled_right_dock_toggle",
    "_enabled_problems_panel_active",
    "_enabled_problems_can_jump",
    "_enabled_entity_selected",
]

# Shortcut scope constants
SHORTCUT_SCOPE_GLOBAL = "global"
SHORTCUT_SCOPE_INLINE_RENAME = "text_input.inline_rename"
SHORTCUT_SCOPE_PROJECT_EXPLORER = "project_explorer"
SHORTCUT_SCOPE_PROJECT_EXPLORER_CONTEXT_MENU = "project_explorer.context_menu"


def _is_web_runtime() -> bool:
    return sys.platform == "emscripten" or os.environ.get("PYGBAG") == "1"


def _get_editor(window: Any) -> Any | None:
    return getattr(window, "editor_controller", None) if window is not None else None


def _enabled_always(_controller: Any, _window: Any) -> bool:
    return True


def _enabled_has_selection(controller: Any, _window: Any) -> bool:
    return getattr(controller, "selected_entity", None) is not None


def _enabled_has_selection_or_project_explorer(controller: Any, _window: Any) -> bool:
    if getattr(controller, "selected_entity", None) is not None:
        return True
    project_ctrl = getattr(controller, "project_explorer", None)
    if project_ctrl is None:
        return False
    count = getattr(project_ctrl, "selection_count", None)
    if callable(count):
        result = count()
        return int(result) > 0 if isinstance(result, (int, float)) else False
    return False


def _enabled_can_undo(controller: Any, _window: Any) -> bool:
    return _history_actions._enabled_can_undo(controller, _window)


def _enabled_can_redo(controller: Any, _window: Any) -> bool:
    return _history_actions._enabled_can_redo(controller, _window)


def _enabled_scene_dirty(controller: Any, _window: Any) -> bool:
    return bool(getattr(controller, "scene_dirty", False))


def _enabled_not_web(_controller: Any, _window: Any) -> bool:
    return not _is_web_runtime()


def _enabled_multiselect(controller: Any, _window: Any) -> bool:
    """Return True if 2+ entities are selected."""
    selected_ids = getattr(controller, "_selected_entity_ids", [])
    return len(selected_ids) >= 2


def _enabled_multiselect_3(controller: Any, _window: Any) -> bool:
    """Return True if 3+ entities are selected (for distribute)."""
    selected_ids = getattr(controller, "_selected_entity_ids", [])
    return len(selected_ids) >= 3


def _enabled_right_dock_toggle(controller: Any, _window: Any) -> bool:
    return getattr(controller, "tool_mode", "") != "ZONE"


def _enabled_problems_panel_active(controller: Any, _window: Any) -> bool:
    """True when Problems panel is the active right dock tab."""
    snapshot = get_dock_snapshot(controller)
    return bool(snapshot is not None and snapshot.right_tab == "Problems")


def _enabled_problems_can_jump(controller: Any, _window: Any) -> bool:
    """True when Problems panel is active, has issues, and selected issue is jump-supported."""
    snapshot = get_dock_snapshot(controller)
    if snapshot is None or snapshot.right_tab != "Problems":
        return False
    problems_ctl = getattr(controller, "problems", None)
    if problems_ctl is None:
        return False
    target = getattr(problems_ctl, "get_selected_jump_target", lambda: None)()
    if not target:
        return False
    # Check if jump is supported for this target
    from engine.editor.problems_jump_model import is_jump_supported  # noqa: PLC0415

    return is_jump_supported(target)


def _enabled_entity_selected(_controller: Any, window: Any) -> bool:
    """Check if an entity is selected."""
    editor = _get_editor(window)
    if editor is None or not getattr(editor, "active", False):
        return False
    return bool(getattr(editor, "_primary_selected_id", None))
