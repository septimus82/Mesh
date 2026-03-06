"""Editor UI Flow Controller.

Handles the logic for "Find Everything" / Command Palette lifecycle,
navigation, preview hooks, and commitment.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional
from engine.editor.editor_protocols import EditorUiFlowHost

if TYPE_CHECKING:
    # Protocol only
    pass

# Import models
from engine.editor.find_everything_model import (
    filter_find_items,
    clamp_selection,
    compute_find_counts,
    build_find_groups,
    flatten_find_groups,
)
from engine.editor.hd2d_preset_preview_model import (
    is_hd2d_preset_command,
    extract_preset_id_from_command,
)
from engine.editor.editor_actions import run_editor_action
from engine.ui_overlays.widget_overlay_helpers import resolve_preserved_selection_index


class EditorUIFlowController:
    """Manages command palette and ephemeral UI flows."""

    def __init__(self, controller: EditorUiFlowHost) -> None:
        self.controller = controller
        
        # Palette State
        self.is_open: bool = False
        self.query: str = ""
        self.selection_index: int = 0
        self.cached_results: List[Any] = []
        self.all_results: List[Any] = []
        self.counts: Dict[str, Any] = {"total": 0, "by_group": {}}
        self.asset_lookup: Dict[str, Any] = {}

    def _result_identity(self, item: Any) -> tuple[str, str] | None:
        kind = str(getattr(item, "kind", "") or "")
        item_id = str(getattr(item, "item_id", "") or "")
        if not kind or not item_id:
            return None
        return (kind, item_id)

    def open_palette(self, initial_query: str = "") -> None:
        """Open the command palette."""
        self.is_open = True
        self.query = initial_query
        self.selection_index = 0
        self._refresh_results()

    def close_palette(self, cancel_preview: bool = True) -> None:
        """Close the command palette."""
        self.is_open = False
        self.query = ""
        self.selection_index = 0
        self.cached_results = []
        
        if cancel_preview:
            self.controller.ui_hd2d_cancel_preview()

    def toggle_palette(self) -> None:
        """Toggle palette state."""
        if self.is_open:
            self.close_palette()
        else:
             self.open_palette()

    def update_query(self, text: str) -> None:
        """Update search query and refresh results."""
        previous_items = list(self.cached_results)
        previous_index = clamp_selection(self.selection_index, len(previous_items))

        self.query = text
        self.selection_index = 0
        self._refresh_results()
        if self.cached_results:
            self.selection_index, _preserved = resolve_preserved_selection_index(
                previous_items,
                self.cached_results,
                previous_index,
                identity_fn=self._result_identity,
                clamp_fn=clamp_selection,
                fallback_index=0,
            )
        self.maybe_preview_from_selection()

    def move_selection(self, delta: int) -> None:
        """Move selection index by delta."""
        if not self.cached_results:
            return
            
        self.selection_index += delta
        self.selection_index = clamp_selection(self.selection_index, len(self.cached_results))
        self.maybe_preview_from_selection()

    def clamp_selection_index(self) -> None:
        """Ensure selection index is valid."""
        self.selection_index = clamp_selection(self.selection_index, len(self.cached_results))

    def _refresh_results(self) -> None:
        """Filter results based on query."""
        items = self._build_items()
        all_results = filter_find_items(items, self.query, limit=None)
        groups = build_find_groups(all_results)
        flattened = flatten_find_groups(groups)
        
        # Cache full results
        self.all_results = list(flattened)
        self.counts = compute_find_counts(all_results, include_zero=True)
        
        # Cache view results (limited)
        results = list(flattened[:8])
        self.cached_results = results
        self.selection_index = clamp_selection(self.selection_index, len(results))

    def _build_items(self) -> List[Any]:
        """Aggregate all searchable items."""
        # Diet V5: Delegate to Host Protocol
        return self.controller.ui_get_palette_items()

    def maybe_preview_from_selection(self) -> None:
        """Check if current selection triggers a preview (e.g., HD2D preset)."""
        if not self.cached_results:
            self.controller.ui_hd2d_cancel_preview()
            return

        # Ensure index valid
        self.clamp_selection_index()
        if self.selection_index < 0 or self.selection_index >= len(self.cached_results):
            self.controller.ui_hd2d_cancel_preview()
            return

        item = self.cached_results[self.selection_index]
        kind = str(getattr(item, "kind", "") or "")
        item_id = str(getattr(item, "item_id", "") or "")

        # Check for HD2D Preset
        if kind == "command" and is_hd2d_preset_command(item_id):
            preset_id = extract_preset_id_from_command(item_id)
            if preset_id:
                self.controller.ui_hd2d_preview(preset_id)
                return

        # Default: cancel preview
        self.controller.ui_hd2d_cancel_preview()

    def commit_selection(self) -> bool:
        """Commit the current selection and close palette.
        
        Returns:
            True if action was executed.
        """
        if not self.cached_results:
            return False
            
        self.clamp_selection_index()
        if self.selection_index < 0 or self.selection_index >= len(self.cached_results):
            return False
            
        item = self.cached_results[self.selection_index]
        kind = str(getattr(item, "kind", "") or "")
        item_id = str(getattr(item, "item_id", "") or "")
        
        # Close first
        self.close_palette(cancel_preview=False)
        
        # Handle specific commit types
        if kind == "command":
            # Delegate to controller to handle command activation
            if self.controller.ui_activate_command(item_id):
                 return True
                 
            # Special case: HD2D Presets
            if is_hd2d_preset_command(item_id):
                 preset_id = extract_preset_id_from_command(item_id)
                 if preset_id:
                     return self.controller.ui_hd2d_commit(preset_id)
            
            # General Command
            # Use property 'window' if available or explicit cast?
            # Implemented 'window' on Protocol for this exact compat reason.
            win = getattr(self.controller, "window", None)
            return run_editor_action(item_id, self.controller, win)
            
        elif kind == "asset":
            return self.controller.ui_activate_asset(item_id)
            
        elif kind == "scene":
            return self.controller.ui_activate_scene(item_id)
                
        elif kind == "entity":
            return self.controller.ui_activate_entity(item_id)
                
        elif kind == "problem":
             return self.controller.ui_activate_problem(item_id)
                
        return False
