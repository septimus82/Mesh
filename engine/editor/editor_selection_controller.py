"""Editor selection controller logic.

Handles:
- Single and multi-selection
- Inspector interaction helpers
- Selection state management
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController

class EditorSelectionController:
    """Manages entity selection state."""

    def __init__(self, controller: EditorModeController) -> None:
        self.controller = controller

        # Selection state
        self.primary_selected_id: Optional[str] = None
        self.selected_ids: List[str] = []

    def clear_selection(self) -> None:
        """Clear all selection."""
        self.primary_selected_id = None
        self.selected_ids.clear()

        # Clear arcade sprites if applicable
        if hasattr(self.controller, "selection_group"):
            # If selection_group is a SpriteList, clear it
            sg = getattr(self.controller, "selection_group", None)
            if sg is not None and hasattr(sg, "clear"):
                sg.clear()

    def select_entity(self, entity_id: str, additive: bool = False) -> None:
        """Select an entity by ID."""
        if not entity_id:
            return

        if not additive:
            self.clear_selection()

        self.primary_selected_id = entity_id
        if entity_id not in self.selected_ids:
            self.selected_ids.append(entity_id)

        # Trigger UI updates via main controller
        # In a full refactor, this would be an event/signal
        if hasattr(self.controller, "_update_inspector"):
            getattr(self.controller, "_update_inspector")()

    def deselect_entity(self, entity_id: str) -> None:
        """Deselect an entity."""
        if entity_id in self.selected_ids:
            self.selected_ids.remove(entity_id)

        if self.primary_selected_id == entity_id:
            if self.selected_ids:
                # Pick the last one added as new primary? Or first?
                # Original editor behavior: usually the last one selected is primary.
                # If we remove primary, maybe fallback to the new last one?
                self.primary_selected_id = self.selected_ids[-1]
            else:
                self.primary_selected_id = None

    def get_selected_count(self) -> int:
        return len(self.selected_ids)

    def is_selected(self, entity_id: str) -> bool:
        return entity_id in self.selected_ids
