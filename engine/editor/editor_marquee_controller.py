"""Editor marquee selection controller.

Extracted from editor_controller.py to encapsulate marquee box selection
operations: begin, update, end, cancel, and reset.
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple, TYPE_CHECKING

from engine.logging_tools import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class EditorMarqueeController:
    """Encapsulates marquee box selection operations."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor
        # Marquee selection state
        self._active: bool = False
        self._start_world: Tuple[float, float] | None = None
        self._end_world: Tuple[float, float] | None = None
        self._shift: bool = False

    @property
    def active(self) -> bool:
        """Whether marquee selection is currently active."""
        return self._active

    @active.setter
    def active(self, value: bool) -> None:
        self._active = value

    @property
    def start_world(self) -> Tuple[float, float] | None:
        """The marquee start position in world coordinates."""
        return self._start_world

    @start_world.setter
    def start_world(self, value: Tuple[float, float] | None) -> None:
        self._start_world = value

    @property
    def end_world(self) -> Tuple[float, float] | None:
        """The marquee end position in world coordinates."""
        return self._end_world

    @end_world.setter
    def end_world(self, value: Tuple[float, float] | None) -> None:
        self._end_world = value

    @property
    def shift(self) -> bool:
        """Whether shift modifier was held."""
        return self._shift

    @shift.setter
    def shift(self, value: bool) -> None:
        self._shift = value

    def begin(self, world_x: float, world_y: float, shift: bool) -> None:
        """Begin a marquee box selection.

        Args:
            world_x: Start X in world coordinates.
            world_y: Start Y in world coordinates.
            shift: Whether Shift modifier is held.
        """
        self._active = True
        self._start_world = (world_x, world_y)
        self._end_world = (world_x, world_y)
        self._shift = shift

    def update(self, world_x: float, world_y: float) -> None:
        """Update marquee end point during drag.

        Args:
            world_x: Current X in world coordinates.
            world_y: Current Y in world coordinates.
        """
        if self._active:
            self._end_world = (world_x, world_y)

    def end(self) -> None:
        """Commit marquee selection and deactivate."""
        if not self._active:
            return

        from engine.editor.marquee_select import (  # noqa: PLC0415
            rect_from_points,
            compute_marquee_candidates,
            apply_marquee_selection,
        )
        from engine.editor.selection_outline import resolve_entity_bounds  # noqa: PLC0415
        from engine.editor_runtime.state import get_sprite_for_entity_id  # noqa: PLC0415

        editor = self._editor
        start = self._start_world
        end = self._end_world

        if start is None or end is None:
            self.reset()
            return

        # Build marquee rect
        marquee_rect = rect_from_points(start, end)

        # Build entity bounds list
        entity_bounds: list[tuple[str, Any]] = []
        sc = getattr(editor.window, "scene_controller", None)
        if sc is not None:
            scene_data = getattr(sc, "current_scene_data", None)
            if isinstance(scene_data, dict):
                entities = scene_data.get("entities", [])
                if isinstance(entities, list):
                    for entity in entities:
                        if isinstance(entity, dict):
                            eid = entity.get("id")
                            if eid:
                                sprite = get_sprite_for_entity_id(editor, eid)
                                rect = resolve_entity_bounds(entity, sprite)
                                if rect is not None:
                                    entity_bounds.append((eid, rect))

        # Compute candidates
        candidates = compute_marquee_candidates(marquee_rect, entity_bounds)

        # Apply selection
        current_selected = list(getattr(editor, "_selected_entity_ids", []))
        new_selection = apply_marquee_selection(current_selected, candidates, self._shift)

        # Update selection state
        editor._selected_entity_ids = new_selection
        editor._primary_entity_id = new_selection[0] if new_selection else None

        # Update selected_entity sprite reference
        if editor._primary_entity_id:
            editor.selected_entity = get_sprite_for_entity_id(editor, editor._primary_entity_id)
        else:
            editor.selected_entity = None

        self.reset()

    def cancel(self) -> None:
        """Cancel marquee selection without committing."""
        self.reset()

    def reset(self) -> None:
        """Reset marquee state."""
        self._active = False
        self._start_world = None
        self._end_world = None
        self._shift = False
