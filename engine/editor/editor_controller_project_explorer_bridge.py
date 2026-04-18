"""Binder: Project Explorer & Undo History delegation shims.

Extracted from ``engine.editor_controller`` to reduce god-class bloat.
Every function takes ``self`` (an ``EditorModeController``) as first arg.
``bind_project_explorer_bridge_methods`` monkey-patches them onto the class.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController


# -- Project Explorer shims -------------------------------------------------

def _refresh_project_explorer_rows(self: "EditorModeController") -> None:
    self.project_explorer_actions.refresh_rows()


def _project_explorer_display_rows(self: "EditorModeController") -> list[Any]:
    return self.project_explorer_actions.get_display_rows()


def _project_explorer_selectable_rows(self: "EditorModeController") -> list[Any]:
    return self.project_explorer_actions.get_selectable_rows()


def _activate_project_explorer_selected(self: "EditorModeController") -> bool:
    return self.project_explorer_actions.activate_selected()


def _project_explorer_handle_mouse_click(self: "EditorModeController", x: float, y: float, button: int, modifiers: int) -> bool:
    return self.project_explorer_actions.handle_mouse_click(x, y, button, modifiers)


def _activate_project_recent(self: "EditorModeController", recent: Any) -> bool:
    return self.project_explorer_actions.activate_recent(recent)


def _push_project_recent(self: "EditorModeController", kind: str, rel_path: str, label: str) -> None:
    self.project_explorer_actions.push_recent(kind, rel_path, label)


def _project_explorer_recent_payloads(self: "EditorModeController") -> list[dict[str, Any]]:
    return self.project_explorer_actions.get_recent_payloads()


def _clear_project_recents(self: "EditorModeController") -> bool:
    return self.project_explorer_actions.clear_recents()


def reveal_in_project_explorer(self: "EditorModeController", target_path: str) -> bool:
    return self.project_explorer_actions.reveal_in_explorer(target_path)


def reveal_current_in_project_explorer(self: "EditorModeController") -> bool:
    return self.project_explorer_actions.reveal_current_in_explorer()


def _get_current_scene_path(self: "EditorModeController") -> str | None:
    return self.project_explorer_actions.get_current_scene_path()


def _get_selected_entity_asset_path(self: "EditorModeController") -> str | None:
    return self.project_explorer_actions.get_selected_entity_asset_path()


def copy_project_explorer_selected_path(self: "EditorModeController") -> bool:
    return self.project_explorer_actions.copy_selected_path()


def _try_copy_to_os_clipboard(self: "EditorModeController", text: str) -> None:
    self.project_explorer_actions.try_copy_to_os_clipboard(text)


def safe_rename_selected_asset(self: "EditorModeController", new_name: str) -> bool:
    return self.project_explorer_actions.safe_rename_selected_asset(new_name)


def safe_move_selected_asset(self: "EditorModeController", dest_folder_rel: str) -> bool:
    return self.project_explorer_actions.safe_move_selected_asset(dest_folder_rel)


def safe_move_selected_assets(self: "EditorModeController", dest_folder_rel: str) -> bool:
    return self.project_explorer_actions.safe_move_selected_assets(dest_folder_rel)


def prompt_project_explorer_move_destination(self: "EditorModeController", on_confirm) -> bool:
    return self.project_explorer_actions.prompt_move_destination(on_confirm)


def _get_selected_project_entry_path(self: "EditorModeController") -> str | None:
    return self.project_explorer_actions.get_selected_project_entry_path()


# -- Undo History shims -----------------------------------------------------

def get_undo_history_entries(self: "EditorModeController") -> list[Any]:
    return self.history.get_entries()


def get_filtered_undo_history_entries(self: "EditorModeController") -> list[Any]:
    return self.history.get_filtered_entries()


def jump_undo_history_to(self: "EditorModeController", cursor_index: int) -> bool:
    return self.history.jump_to(cursor_index)


def _history_handle_mouse_click(self: "EditorModeController", x: float, y: float, button: int) -> bool:
    return self.history.handle_mouse_click(x, y, button)


# -- Problems Panel shims --------------------------------------------------

def _reveal_in_project_explorer_problems(self: "EditorModeController", path: str) -> bool:
    """Reveal a path in the Project Explorer.

    DELEGATED to EditorProblemsActionsController.
    """
    return self.problems_actions._reveal_in_project_explorer(path)


# ---------------------------------------------------------------------------
# Binder
# ---------------------------------------------------------------------------

def bind_project_explorer_bridge_methods(cls: Any) -> None:
    # Project Explorer
    cls._refresh_project_explorer_rows = _refresh_project_explorer_rows
    cls._project_explorer_display_rows = _project_explorer_display_rows
    cls._project_explorer_selectable_rows = _project_explorer_selectable_rows
    cls._activate_project_explorer_selected = _activate_project_explorer_selected
    cls._project_explorer_handle_mouse_click = _project_explorer_handle_mouse_click
    cls._activate_project_recent = _activate_project_recent
    cls._push_project_recent = _push_project_recent
    cls._project_explorer_recent_payloads = _project_explorer_recent_payloads
    cls._clear_project_recents = _clear_project_recents
    cls.reveal_in_project_explorer = reveal_in_project_explorer
    cls.reveal_current_in_project_explorer = reveal_current_in_project_explorer
    cls._get_current_scene_path = _get_current_scene_path
    cls._get_selected_entity_asset_path = _get_selected_entity_asset_path
    cls.copy_project_explorer_selected_path = copy_project_explorer_selected_path
    cls._try_copy_to_os_clipboard = _try_copy_to_os_clipboard
    cls.safe_rename_selected_asset = safe_rename_selected_asset
    cls.safe_move_selected_asset = safe_move_selected_asset
    cls.safe_move_selected_assets = safe_move_selected_assets
    cls.prompt_project_explorer_move_destination = prompt_project_explorer_move_destination
    cls._get_selected_project_entry_path = _get_selected_project_entry_path
    # Undo History
    cls.get_undo_history_entries = get_undo_history_entries
    cls.get_filtered_undo_history_entries = get_filtered_undo_history_entries
    cls.jump_undo_history_to = jump_undo_history_to
    cls._history_handle_mouse_click = _history_handle_mouse_click
    # Problems
    cls._reveal_in_project_explorer = _reveal_in_project_explorer_problems
