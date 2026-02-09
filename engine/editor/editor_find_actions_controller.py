"""Controller for find/activate actions (command palette, find everything).

This module extracts _activate_find_* methods from EditorModeController
for the Vertical Slice Diet V2.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController


class EditorFindActionsController:
    """Manages find/activate actions for command palette and find-everything."""

    def __init__(self, editor: "EditorModeController") -> None:
        self._editor = editor

    def activate_find_command(self, command_id: str) -> bool:
        """Activate a command from find-everything or command palette."""
        from engine.editor.hd2d_preset_preview_model import (  # noqa: PLC0415
            is_hd2d_preset_command,
            extract_preset_id_from_command,
        )

        editor = self._editor

        # Handle HD2D presets specially - commit via our method
        if is_hd2d_preset_command(command_id):
            preset_id = extract_preset_id_from_command(command_id)
            if preset_id:
                return editor.commit_hd2d_preset(preset_id)
            return False

        # Normal command execution
        from engine.editor_commands import run_command  # noqa: PLC0415

        return run_command(command_id, editor.window)

    def activate_find_scene(self, scene_id: str) -> bool:
        """Activate a scene from find-everything."""
        return self._editor._open_scene_by_id(scene_id)

    def activate_find_entity(self, entity_id: str) -> bool:
        """Activate an entity from find-everything (select and focus camera)."""
        from engine.editor_runtime.state import apply_selection, get_sprite_for_entity_id  # noqa: PLC0415
        from engine.editor_runtime.input import _focus_camera_on_entity  # noqa: PLC0415

        editor = self._editor
        sprite = get_sprite_for_entity_id(editor, entity_id)
        if sprite is None:
            return False
        apply_selection(editor, sprite, shift=False)
        editor._entity_panels_selected_id = entity_id
        editor._refresh_entity_panels_list(sync_selected=True)
        _focus_camera_on_entity(editor)
        return True

    def activate_find_asset(self, asset_path: str) -> bool:
        """Activate an asset from find-everything."""
        return self._editor.asset_browser.activate_find_asset(asset_path)

    def spawn_find_asset(self, asset_path: str) -> bool:
        """Spawn an asset from find-everything."""
        return self._editor.asset_browser._spawn_find_asset(asset_path)

    def copy_find_asset_path(self, asset_path: str) -> bool:
        """Copy asset path to clipboard from find-everything."""
        return self._editor.asset_browser._copy_find_asset_path(asset_path)

    def activate_find_problem(self, issue_id: str) -> bool:
        """Activate a problem from find-everything (show in Problems panel)."""
        editor = self._editor
        issues = list(editor.problems.issues)
        if not issues:
            issues = editor.search.get_find_everything_problems()
            editor.problems.set_issues(list(issues))

        # Search in potentially re-sorted list
        current_issues = editor.problems.issues
        index = next(
            (i for i, issue in enumerate(current_issues) if getattr(issue, "issue_id", None) == issue_id),
            None,
        )

        if index is None:
            return False
        editor.dock.apply_tab_change(editor, "right", "Problems")
        editor.problems.set_selected_index(index)
        editor.problems.preview_open = True
        return True
