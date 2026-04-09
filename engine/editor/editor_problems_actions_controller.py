"""Controller for problems panel actions that require editor context.

This module extracts problems-related action methods from EditorModeController
for the Vertical Slice Diet V2.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController


class EditorProblemsActionsController:
    """Manages problems panel actions (jump, copy, reveal) that need editor context."""

    def __init__(self, editor: "EditorModeController") -> None:
        self._editor = editor

    def jump_to_selected(self) -> bool:
        """Jump to the selected problem (load scene, select entity, reveal in explorer)."""
        from engine.editor.problems_jump_model import is_jump_supported, format_location_text  # noqa: PLC0415

        editor = self._editor
        target = editor.problems.get_selected_jump_target()
        if not target or not is_jump_supported(target):
            return False

        kind = target.get("kind", "none")
        scene_path = target.get("scene_path")
        entity_id = target.get("entity_id")
        path = target.get("path")

        # Jump to scene (and optionally select entity)
        if kind in ("scene", "entity") and scene_path:
            if not editor._open_scene_by_id(scene_path):
                self._toast(f"Failed to load scene: {scene_path}")
                return False

            # If entity jump, select the entity
            if kind == "entity" and entity_id:
                editor._selection_ctl.primary_selected_id = entity_id
                self._toast(f"Jumped to entity: {entity_id}")
            else:
                self._toast(f"Opened scene: {scene_path}")

            # Reveal in Project Explorer if path available
            if path:
                self._reveal_in_project_explorer(path)

            return True

        # Reveal file in explorer (future: for file-only issues)
        if kind == "file" and path:
            if self._reveal_in_project_explorer(path):
                loc_text = format_location_text(target)
                self._toast(f"Revealed: {loc_text}")
                return True

        return False

    def copy_location(self) -> bool:
        """Copy the selected problem's location to clipboard (native only)."""
        from engine.editor.problems_jump_model import format_location_text  # noqa: PLC0415
        from engine.tooling_runtime.clipboard import try_copy_to_clipboard  # noqa: PLC0415

        editor = self._editor
        target = editor.problems.get_selected_jump_target()
        if not target:
            return False

        loc_text = format_location_text(target)
        if not loc_text:
            return False

        success = try_copy_to_clipboard(loc_text)
        if success:
            self._toast(f"Copied: {loc_text}")
        else:
            self._toast("Clipboard unavailable (headless/web)")

        return success

    def _reveal_in_project_explorer(self, path: str) -> bool:
        """Reveal a path in the Project Explorer."""
        # Use project explorer actions controller to reveal.
        return bool(self._editor.project_explorer_actions.reveal_path(path))

    def _toast(self, message: str, seconds: float = 2.5) -> None:
        """Show a toast notification for problems panel actions."""
        hud = getattr(self._editor.window, "player_hud", None)
        toaster = getattr(hud, "enqueue_toast", None) if hud is not None else None
        if callable(toaster):
            toaster(message, seconds=seconds)
