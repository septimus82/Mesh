"""Editor alt-drag duplicate controller.

Extracted from editor_controller.py to encapsulate alt-drag duplicate
operations: begin, update, end, cancel, and apply command.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from engine.logging_tools import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class EditorDuplicateController:
    """Encapsulates alt-drag duplicate operations."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor
        # Alt-drag duplicate state
        self._active: bool = False
        self._specs: Tuple[Any, ...] | None = None
        self._pivot_new_id: str | None = None
        self._drag_start_world: Tuple[float, float] | None = None
        self._last_world: Tuple[float, float] | None = None
        self._original_selection: List[str] | None = None
        self._original_primary: str | None = None

    @property
    def active(self) -> bool:
        """Whether alt-drag duplicate is currently active."""
        return self._active

    @active.setter
    def active(self, value: bool) -> None:
        self._active = value

    @property
    def specs(self) -> Tuple[Any, ...] | None:
        """The duplicate specs."""
        return self._specs

    @specs.setter
    def specs(self, value: Tuple[Any, ...] | None) -> None:
        self._specs = value

    @property
    def pivot_new_id(self) -> str | None:
        """The pivot new entity ID."""
        return self._pivot_new_id

    @pivot_new_id.setter
    def pivot_new_id(self, value: str | None) -> None:
        self._pivot_new_id = value

    @property
    def drag_start_world(self) -> Tuple[float, float] | None:
        """The drag start world position."""
        return self._drag_start_world

    @drag_start_world.setter
    def drag_start_world(self, value: Tuple[float, float] | None) -> None:
        self._drag_start_world = value

    @property
    def last_world(self) -> Tuple[float, float] | None:
        """The last world position."""
        return self._last_world

    @last_world.setter
    def last_world(self, value: Tuple[float, float] | None) -> None:
        self._last_world = value

    @property
    def original_selection(self) -> List[str] | None:
        """The original selection before duplicate."""
        return self._original_selection

    @original_selection.setter
    def original_selection(self, value: List[str] | None) -> None:
        self._original_selection = value

    @property
    def original_primary(self) -> str | None:
        """The original primary entity ID."""
        return self._original_primary

    @original_primary.setter
    def original_primary(self, value: str | None) -> None:
        self._original_primary = value

    def begin(self, world_x: float, world_y: float) -> None:
        """Begin alt-drag duplicate operation.

        Duplicates selected entities immediately and starts dragging them.

        Args:
            world_x: Start X in world coordinates.
            world_y: Start Y in world coordinates.
        """
        from engine.editor.editor_alt_drag_duplicate_ops import (  # noqa: PLC0415
            duplicate_entities_in_scene,
        )
        from engine.editor_runtime.state import get_sprite_for_entity_id  # noqa: PLC0415

        editor = self._editor
        selected_ids = list(getattr(editor, "_selected_entity_ids", []))
        if not selected_ids:
            return

        # Store original selection for cancel
        self._original_selection = selected_ids.copy()
        self._original_primary = getattr(editor, "_primary_entity_id", None)

        # Get scene data
        sc = getattr(editor.window, "scene_controller", None)
        if sc is None:
            return
        scene_data = getattr(sc, "_loaded_scene_data", None)
        if not isinstance(scene_data, dict):
            return

        # Duplicate entities into scene
        new_scene, specs = duplicate_entities_in_scene(scene_data, selected_ids)

        if not specs:
            return

        # Update scene data in place
        sc._loaded_scene_data = new_scene

        # Create sprites for duplicated entities
        entities = new_scene.get("entities", [])
        for spec in specs:
            # Find the new entity data
            new_entity_data = None
            for entity in entities:
                eid = entity.get("id") or entity.get("entity_id") or entity.get("name") or entity.get("mesh_name")
                if eid == spec.new_id:
                    new_entity_data = entity
                    break
            if new_entity_data:
                editor._create_entity_internal(new_entity_data)

        # Determine pivot (copy of primary, or first)
        primary_src = self._original_primary
        pivot_new_id: str | None = None
        for spec in specs:
            if spec.src_id == primary_src:
                pivot_new_id = spec.new_id
                break
        if pivot_new_id is None and specs:
            pivot_new_id = specs[0].new_id

        # Set selection to duplicated entities
        new_selection = [spec.new_id for spec in specs]
        editor._selected_entity_ids = new_selection
        editor._primary_entity_id = pivot_new_id

        # Update selected_entity sprite reference
        if pivot_new_id:
            editor.selected_entity = get_sprite_for_entity_id(editor, pivot_new_id)

        # Store state
        self._active = True
        self._specs = tuple(specs)
        self._pivot_new_id = pivot_new_id
        self._drag_start_world = (world_x, world_y)
        self._last_world = (world_x, world_y)

        editor._mark_dirty()

    def update(self, world_x: float, world_y: float) -> None:
        """Update alt-drag duplicate positions during drag.

        Args:
            world_x: Current X in world coordinates.
            world_y: Current Y in world coordinates.
        """
        from engine.editor.editor_alt_drag_duplicate_ops import (  # noqa: PLC0415
            apply_drag_delta_to_specs,
        )
        from engine.editor_runtime.state import get_sprite_for_entity_id  # noqa: PLC0415

        editor = self._editor

        if not self._active or self._specs is None:
            return

        start = self._drag_start_world
        if start is None:
            return

        # Compute delta
        delta_xy = (world_x - start[0], world_y - start[1])

        # Get snap settings
        snap_enabled = getattr(editor, "snap_enabled", True)
        snap_mode = getattr(editor, "snap_mode", "grid16")
        tile_size = int(getattr(editor, "grid_size", 16))

        # Apply drag delta with snapping
        updated_specs = apply_drag_delta_to_specs(
            list(self._specs),
            delta_xy,
            snap_enabled,
            snap_mode,
            tile_size,
            self._pivot_new_id,
        )

        # Update specs
        self._specs = tuple(updated_specs)
        self._last_world = (world_x, world_y)

        # Apply positions to sprites
        for spec in updated_specs:
            sprite = get_sprite_for_entity_id(editor, spec.new_id)
            if sprite:
                sprite.center_x = spec.end_xy[0]
                sprite.center_y = spec.end_xy[1]
                # Also update entity data
                entity_data = getattr(sprite, "mesh_entity_data", None)
                if isinstance(entity_data, dict):
                    entity_data["x"] = spec.end_xy[0]
                    entity_data["y"] = spec.end_xy[1]

    def cancel(self) -> None:
        """Cancel alt-drag duplicate and remove duplicated entities."""
        from engine.editor.editor_alt_drag_duplicate_ops import (  # noqa: PLC0415
            remove_alt_drag_duplicates,
            AltDragDuplicateCommand,
        )
        from engine.editor_runtime.state import get_sprite_for_entity_id  # noqa: PLC0415

        editor = self._editor

        if not self._active:
            return

        specs = self._specs
        if specs:
            # Remove sprites for duplicated entities
            for spec in specs:
                sprite = get_sprite_for_entity_id(editor, spec.new_id)
                if sprite:
                    editor._delete_entity_internal(sprite)

            # Also remove from scene data
            sc = getattr(editor.window, "scene_controller", None)
            if sc is not None:
                scene_data = getattr(sc, "_loaded_scene_data", None)
                if isinstance(scene_data, dict):
                    cmd = AltDragDuplicateCommand(specs=specs)
                    new_scene = remove_alt_drag_duplicates(scene_data, cmd)
                    sc._loaded_scene_data = new_scene

        # Restore original selection
        if self._original_selection is not None:
            editor._selected_entity_ids = self._original_selection
            editor._primary_entity_id = self._original_primary
            if self._original_primary:
                editor.selected_entity = get_sprite_for_entity_id(editor, self._original_primary)
            else:
                editor.selected_entity = None

        self.reset()
        editor._mark_dirty()

    def end(self) -> None:
        """Commit alt-drag duplicate and push undo command."""
        from engine.editor.editor_alt_drag_duplicate_ops import AltDragDuplicateCommand  # noqa: PLC0415

        editor = self._editor

        if not self._active:
            return

        specs = self._specs
        if not specs:
            self.reset()
            return

        # Get snap settings for command
        snap_enabled = getattr(editor, "snap_enabled", True)
        snap_mode = getattr(editor, "snap_mode", "grid16")

        # Build command
        cmd = AltDragDuplicateCommand(
            kind="alt_drag_duplicate",
            specs=specs,
            pivot_src_id=self._original_primary,
            pivot_new_id=self._pivot_new_id,
            snap_enabled=snap_enabled,
            snap_mode=snap_mode,
        )

        # Push undo command
        editor._push_command(cmd.to_dict())

        # Sync final positions to scene data
        sc = getattr(editor.window, "scene_controller", None)
        if sc is not None:
            scene_data = getattr(sc, "_loaded_scene_data", None)
            if isinstance(scene_data, dict):
                entities = scene_data.get("entities", [])
                if isinstance(entities, list):
                    for spec in specs:
                        for entity in entities:
                            eid = entity.get("id") or entity.get("entity_id") or entity.get("name") or entity.get("mesh_name")
                            if eid == spec.new_id:
                                entity["x"] = spec.end_xy[0]
                                entity["y"] = spec.end_xy[1]
                                break

        self.reset()

    def reset(self) -> None:
        """Reset alt-drag duplicate state."""
        self._active = False
        self._specs = None
        self._pivot_new_id = None
        self._drag_start_world = None
        self._last_world = None
        self._original_selection = None
        self._original_primary = None

    def apply_command(self, cmd: Dict[str, Any]) -> None:
        """Apply an alt-drag duplicate command (redo)."""
        from engine.editor.editor_alt_drag_duplicate_ops import (  # noqa: PLC0415
            AltDragDuplicateCommand,
            apply_alt_drag_duplicate,
        )

        editor = self._editor
        alt_cmd = AltDragDuplicateCommand.from_dict(cmd)

        # Apply to scene data
        sc = getattr(editor.window, "scene_controller", None)
        if sc is not None:
            scene_data = getattr(sc, "_loaded_scene_data", None)
            if isinstance(scene_data, dict):
                new_scene = apply_alt_drag_duplicate(scene_data, alt_cmd)
                sc._loaded_scene_data = new_scene

                # Create sprites for duplicated entities
                entities = new_scene.get("entities", [])
                for spec in alt_cmd.specs:
                    # Find the new entity data
                    for entity in entities:
                        eid = entity.get("id") or entity.get("entity_id") or entity.get("name") or entity.get("mesh_name")
                        if eid == spec.new_id:
                            editor._create_entity_internal(entity)
                            break
