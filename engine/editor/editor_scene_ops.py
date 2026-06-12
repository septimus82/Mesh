"""Editor scene operations controller logic.

Handles:
- Dirty state tracking
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from engine.editor.state import EditorDirtyState

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController

class EditorSceneOpsController:
    """Manages scene dirty state."""

    def __init__(self, controller: EditorModeController) -> None:
        self.controller = controller

        # Dirty state
        self.scene_dirty: bool = False
        self.dirty_state = EditorDirtyState()

    def mark_dirty(self) -> None:
        """Mark the scene as dirty (unsaved changes)."""
        self.scene_dirty = True
        self.dirty_state.is_dirty = True

    def mark_clean(self) -> None:
        """Mark the scene as clean (saved)."""
        self.scene_dirty = False
        self.dirty_state.is_dirty = False
