"""Controller for entity CRUD and transform operations.

This module extracts entity operation methods from EditorModeController
for the Vertical Slice Diet V2.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

import engine.optional_arcade as optional_arcade

if TYPE_CHECKING:
    from engine.editor_controller import EditorModeController


class EditorEntityOpsController:
    """Manages entity CRUD operations and transform commands."""

    def __init__(self, editor: "EditorModeController") -> None:
        self._editor = editor

    def find_entity_by_name(self, name: str) -> Any:
        """Find an entity sprite by its mesh_name attribute."""
        for sprite in self._editor.window.scene_controller.all_sprites:
            if getattr(sprite, "mesh_name", "") == name:
                return sprite
        return None

    def find_entity_by_id(self, entity_id: str) -> Any:
        """Find an entity sprite by its entity id in mesh_entity_data."""
        for sprite in self._editor.window.scene_controller.all_sprites:
            data = getattr(sprite, "mesh_entity_data", None)
            if isinstance(data, dict) and data.get("id") == entity_id:
                return sprite
        return None

    def create_entity_internal(self, entity_def: Dict[str, Any]) -> Any:
        """Create an entity from definition and add to scene."""
        editor = self._editor
        sprite = editor.window.scene_controller._create_sprite(entity_def)
        if sprite:
            layer_name = entity_def.get("layer", "entities")
            editor.window.scene_controller.add_sprite_to_layer(sprite, layer_name)
        return sprite

    def delete_entity_internal(self, sprite: Any) -> None:
        """Delete an entity sprite from the scene."""
        editor = self._editor
        # Remove from layers
        for layer in editor.window.scene_controller.layers.values():
            if sprite in layer:
                layer.remove(sprite)

        # Remove from solids if present
        if sprite in editor.window.scene_controller.solid_sprites:
            editor.window.scene_controller.solid_sprites.remove(sprite)

        if editor.selected_entity == sprite:
            editor.selected_entity = None
            editor.inspector.set_inspector_active(False)
            editor.shape.reset_zone_selection_state()
            editor._cancel_hierarchy_rename()

    def apply_rotate_entities_cmd(self, cmd: Dict[str, Any], use_before: bool) -> None:
        """Apply or revert a RotateEntities command."""
        rotates = cmd.get("rotates", [])
        key = "start_rot_deg" if use_before else "end_rot_deg"
        for item in rotates:
            eid = item.get("entity_id")
            rot = item.get(key)
            if eid is None or rot is None:
                continue
            entity = self.find_entity_by_id(eid)
            if entity:
                entity.angle = rot

    def apply_scale_entities_cmd(self, cmd: Dict[str, Any], use_before: bool) -> None:
        """Apply or revert a ScaleEntities command."""
        scales = cmd.get("scales", [])
        key = "start_scale" if use_before else "end_scale"
        for item in scales:
            eid = item.get("entity_id")
            sc = item.get(key)
            if eid is None or sc is None:
                continue
            entity = self.find_entity_by_id(eid)
            if entity:
                entity.scale = sc
