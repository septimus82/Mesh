"""Editor scene operations controller logic.

Handles:
- Command history (undo/redo)
- Dirty state tracking
- Scene mutation wrappers
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional
from engine.editor.state import EditorDirtyState

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController

class EditorSceneOpsController:
    """Manages scene operations and undo stack."""

    def __init__(self, controller: EditorModeController) -> None:
        self.controller = controller
        
        # Undo stack
        self.undo_stack: List[Dict[str, Any]] = []
        self.redo_stack: List[Dict[str, Any]] = []
        self.max_history: int = 50

        # Dirty state
        self.scene_dirty: bool = False
        self.dirty_state = EditorDirtyState()
        
    def push_command(self, cmd: Dict[str, Any]) -> None:
        """Push a command to the undo stack."""
        if not cmd:
            return

        self.undo_stack.append(cmd)
        if len(self.undo_stack) > self.max_history:
            self.undo_stack.pop(0)
            
        self.redo_stack.clear()
        self.mark_dirty()

    def mark_dirty(self) -> None:
        """Mark the scene as dirty (unsaved changes)."""
        self.scene_dirty = True
        self.dirty_state.is_dirty = True

    def mark_clean(self) -> None:
        """Mark the scene as clean (saved)."""
        self.scene_dirty = False
        self.dirty_state.is_dirty = False

    def undo(self) -> Optional[Dict[str, Any]]:
        """Pop command from undo stack and return it for application."""
        if not self.undo_stack:
            return None
            
        cmd = self.undo_stack.pop()
        self.redo_stack.append(cmd)
        self.mark_dirty()
        return cmd

    def redo(self) -> Optional[Dict[str, Any]]:
        """Pop command from redo stack and return it for application."""
        if not self.redo_stack:
            return None
            
        cmd = self.redo_stack.pop()
        self.undo_stack.append(cmd)
        self.mark_dirty()
        return cmd
