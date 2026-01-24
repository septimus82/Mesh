"""Integration contract tests for alt-drag duplicate controller flow.

Tests the editor controller alt-drag duplicate flow - headless, no arcade rendering.
"""

from __future__ import annotations

import copy
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


def make_minimal_scene(entities: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Create a minimal scene with entities."""
    if entities is None:
        entities = [
            {"id": "entity_a", "x": 0.0, "y": 0.0, "sprite": "test_a.png"},
            {"id": "entity_b", "x": 100.0, "y": 100.0, "sprite": "test_b.png"},
        ]
    return {"entities": entities, "settings": {}}


class FakeSprite:
    """Fake sprite for testing."""

    def __init__(self, entity_data: dict[str, Any]) -> None:
        self.mesh_entity_data = entity_data
        self.center_x = float(entity_data.get("x", 0.0))
        self.center_y = float(entity_data.get("y", 0.0))
        self.scale = float(entity_data.get("scale", 1.0))
        self.angle = float(entity_data.get("rotation", 0.0))

    def collides_with_point(self, point: tuple[float, float]) -> bool:
        # Simple bounding box check
        x, y = point
        half_w = 16
        half_h = 16
        return (
            self.center_x - half_w <= x <= self.center_x + half_w
            and self.center_y - half_h <= y <= self.center_y + half_h
        )


class FakeSceneController:
    """Fake scene controller for testing."""

    def __init__(self, scene: dict[str, Any]) -> None:
        self._loaded_scene_data = scene
        self.all_sprites: list[FakeSprite] = []
        self.layers = {"entities": []}
        self.solid_sprites: list[FakeSprite] = []
        self._rebuild_sprites()

    def _rebuild_sprites(self) -> None:
        """Rebuild sprites from scene data."""
        self.all_sprites.clear()
        self.layers["entities"].clear()
        for entity in self._loaded_scene_data.get("entities", []):
            sprite = FakeSprite(entity)
            self.all_sprites.append(sprite)
            self.layers["entities"].append(sprite)

    def _create_sprite(self, entity_def: dict[str, Any]) -> FakeSprite:
        sprite = FakeSprite(entity_def)
        self.all_sprites.append(sprite)
        return sprite

    def add_sprite_to_layer(self, sprite: FakeSprite, layer_name: str) -> None:
        if layer_name not in self.layers:
            self.layers[layer_name] = []
        self.layers[layer_name].append(sprite)

    @property
    def current_scene_data(self) -> dict[str, Any]:
        return self._loaded_scene_data


class FakeEditorController:
    """Fake editor controller with alt-drag duplicate support."""

    def __init__(self, scene: dict[str, Any]) -> None:
        self.active = True
        self.scene_dirty = False
        self.undo_stack: list[dict[str, Any]] = []
        self.redo_stack: list[dict[str, Any]] = []

        self._selected_entity_ids: list[str] = []
        self._primary_entity_id: str | None = None
        self.selected_entity: FakeSprite | None = None

        # Alt-drag duplicate state
        self._alt_dup_active = False
        self._alt_dup_specs: tuple[Any, ...] | None = None
        self._alt_dup_pivot_new_id: str | None = None
        self._alt_dup_drag_start_world: tuple[float, float] | None = None
        self._alt_dup_last_world: tuple[float, float] | None = None
        self._alt_dup_original_selection: list[str] | None = None
        self._alt_dup_original_primary: str | None = None

        # Snap settings
        self.snap_enabled = True
        self.snap_mode = "grid16"
        self.grid_size = 16

        # Fake window with scene controller
        self.window = MagicMock()
        self.window.scene_controller = FakeSceneController(scene)

    def _mark_dirty(self) -> None:
        self.scene_dirty = True

    def _push_command(self, cmd: dict[str, Any]) -> None:
        self.undo_stack.append(cmd)
        self.redo_stack.clear()
        self._mark_dirty()

    def _get_sprite_for_entity_id(self, entity_id: str) -> FakeSprite | None:
        for sprite in self.window.scene_controller.all_sprites:
            data = getattr(sprite, "mesh_entity_data", None)
            if isinstance(data, dict):
                eid = data.get("id") or data.get("entity_id") or data.get("name")
                if eid == entity_id:
                    return sprite
        return None

    def _create_entity_internal(self, entity_def: dict[str, Any]) -> FakeSprite:
        sprite = self.window.scene_controller._create_sprite(entity_def)
        self.window.scene_controller.add_sprite_to_layer(sprite, entity_def.get("layer", "entities"))
        return sprite

    def _delete_entity_internal(self, sprite: FakeSprite) -> None:
        if sprite in self.window.scene_controller.all_sprites:
            self.window.scene_controller.all_sprites.remove(sprite)
        for layer in self.window.scene_controller.layers.values():
            if sprite in layer:
                layer.remove(sprite)
        if self.selected_entity == sprite:
            self.selected_entity = None

    def begin_alt_drag_duplicate(self, world_x: float, world_y: float) -> None:
        """Begin alt-drag duplicate operation."""
        from engine.editor.editor_alt_drag_duplicate_ops import (
            duplicate_entities_in_scene,
        )

        selected_ids = list(self._selected_entity_ids)
        if not selected_ids:
            return

        self._alt_dup_original_selection = selected_ids.copy()
        self._alt_dup_original_primary = self._primary_entity_id

        sc = self.window.scene_controller
        scene_data = sc._loaded_scene_data
        if not isinstance(scene_data, dict):
            return

        new_scene, specs = duplicate_entities_in_scene(scene_data, selected_ids)
        if not specs:
            return

        sc._loaded_scene_data = new_scene

        entities = new_scene.get("entities", [])
        for spec in specs:
            for entity in entities:
                eid = entity.get("id") or entity.get("entity_id") or entity.get("name")
                if eid == spec.new_id:
                    self._create_entity_internal(entity)
                    break

        primary_src = self._alt_dup_original_primary
        pivot_new_id: str | None = None
        for spec in specs:
            if spec.src_id == primary_src:
                pivot_new_id = spec.new_id
                break
        if pivot_new_id is None and specs:
            pivot_new_id = specs[0].new_id

        new_selection = [spec.new_id for spec in specs]
        self._selected_entity_ids = new_selection
        self._primary_entity_id = pivot_new_id

        if pivot_new_id:
            self.selected_entity = self._get_sprite_for_entity_id(pivot_new_id)

        self._alt_dup_active = True
        self._alt_dup_specs = tuple(specs)
        self._alt_dup_pivot_new_id = pivot_new_id
        self._alt_dup_drag_start_world = (world_x, world_y)
        self._alt_dup_last_world = (world_x, world_y)
        self._mark_dirty()

    def update_alt_drag_duplicate(self, world_x: float, world_y: float) -> None:
        """Update alt-drag duplicate positions during drag."""
        from engine.editor.editor_alt_drag_duplicate_ops import apply_drag_delta_to_specs

        if not self._alt_dup_active or self._alt_dup_specs is None:
            return

        start = self._alt_dup_drag_start_world
        if start is None:
            return

        delta_xy = (world_x - start[0], world_y - start[1])

        updated_specs = apply_drag_delta_to_specs(
            list(self._alt_dup_specs),
            delta_xy,
            self.snap_enabled,
            self.snap_mode,
            self.grid_size,
            self._alt_dup_pivot_new_id,
        )

        self._alt_dup_specs = tuple(updated_specs)
        self._alt_dup_last_world = (world_x, world_y)

        for spec in updated_specs:
            sprite = self._get_sprite_for_entity_id(spec.new_id)
            if sprite:
                sprite.center_x = spec.end_xy[0]
                sprite.center_y = spec.end_xy[1]
                entity_data = getattr(sprite, "mesh_entity_data", None)
                if isinstance(entity_data, dict):
                    entity_data["x"] = spec.end_xy[0]
                    entity_data["y"] = spec.end_xy[1]

    def cancel_alt_drag_duplicate(self) -> None:
        """Cancel alt-drag duplicate and remove duplicated entities."""
        from engine.editor.editor_alt_drag_duplicate_ops import (
            AltDragDuplicateCommand,
            remove_alt_drag_duplicates,
        )

        if not self._alt_dup_active:
            return

        specs = self._alt_dup_specs
        if specs:
            for spec in specs:
                sprite = self._get_sprite_for_entity_id(spec.new_id)
                if sprite:
                    self._delete_entity_internal(sprite)

            sc = self.window.scene_controller
            scene_data = sc._loaded_scene_data
            if isinstance(scene_data, dict):
                cmd = AltDragDuplicateCommand(specs=specs)
                new_scene = remove_alt_drag_duplicates(scene_data, cmd)
                sc._loaded_scene_data = new_scene

        if self._alt_dup_original_selection is not None:
            self._selected_entity_ids = self._alt_dup_original_selection
            self._primary_entity_id = self._alt_dup_original_primary
            if self._alt_dup_original_primary:
                self.selected_entity = self._get_sprite_for_entity_id(self._alt_dup_original_primary)

        self._reset_alt_drag_duplicate()
        self._mark_dirty()

    def end_alt_drag_duplicate(self) -> None:
        """Commit alt-drag duplicate and push undo command."""
        from engine.editor.editor_alt_drag_duplicate_ops import AltDragDuplicateCommand

        if not self._alt_dup_active:
            return

        specs = self._alt_dup_specs
        if not specs:
            self._reset_alt_drag_duplicate()
            return

        cmd = AltDragDuplicateCommand(
            kind="alt_drag_duplicate",
            specs=specs,
            pivot_src_id=self._alt_dup_original_primary,
            pivot_new_id=self._alt_dup_pivot_new_id,
            snap_enabled=self.snap_enabled,
            snap_mode=self.snap_mode,
        )

        self._push_command(cmd.to_dict())

        sc = self.window.scene_controller
        scene_data = sc._loaded_scene_data
        if isinstance(scene_data, dict):
            entities = scene_data.get("entities", [])
            if isinstance(entities, list):
                for spec in specs:
                    for entity in entities:
                        eid = entity.get("id") or entity.get("entity_id") or entity.get("name")
                        if eid == spec.new_id:
                            entity["x"] = spec.end_xy[0]
                            entity["y"] = spec.end_xy[1]
                            break

        self._reset_alt_drag_duplicate()

    def _reset_alt_drag_duplicate(self) -> None:
        """Reset alt-drag duplicate state."""
        self._alt_dup_active = False
        self._alt_dup_specs = None
        self._alt_dup_pivot_new_id = None
        self._alt_dup_drag_start_world = None
        self._alt_dup_last_world = None
        self._alt_dup_original_selection = None
        self._alt_dup_original_primary = None

    def undo(self) -> None:
        """Undo the last command."""
        if not self.undo_stack:
            return
        cmd = self.undo_stack.pop()
        self.redo_stack.append(cmd)
        self._revert_command(cmd)
        self._mark_dirty()

    def redo(self) -> None:
        """Redo the last undone command."""
        if not self.redo_stack:
            return
        cmd = self.redo_stack.pop()
        self.undo_stack.append(cmd)
        self._apply_command(cmd)
        self._mark_dirty()

    def _revert_command(self, cmd: dict[str, Any]) -> None:
        """Revert a command (undo)."""
        from engine.editor.editor_alt_drag_duplicate_ops import (
            AltDragDuplicateCommand,
            remove_alt_drag_duplicates,
        )

        if cmd.get("type") == "AltDragDuplicate":
            alt_cmd = AltDragDuplicateCommand.from_dict(cmd)
            for spec in alt_cmd.specs:
                sprite = self._get_sprite_for_entity_id(spec.new_id)
                if sprite:
                    self._delete_entity_internal(sprite)

            sc = self.window.scene_controller
            scene_data = sc._loaded_scene_data
            if isinstance(scene_data, dict):
                new_scene = remove_alt_drag_duplicates(scene_data, alt_cmd)
                sc._loaded_scene_data = new_scene

    def _apply_command(self, cmd: dict[str, Any]) -> None:
        """Apply a command (redo)."""
        from engine.editor.editor_alt_drag_duplicate_ops import (
            AltDragDuplicateCommand,
            apply_alt_drag_duplicate,
        )

        if cmd.get("type") == "AltDragDuplicate":
            alt_cmd = AltDragDuplicateCommand.from_dict(cmd)

            sc = self.window.scene_controller
            scene_data = sc._loaded_scene_data
            if isinstance(scene_data, dict):
                new_scene = apply_alt_drag_duplicate(scene_data, alt_cmd)
                sc._loaded_scene_data = new_scene

                entities = new_scene.get("entities", [])
                for spec in alt_cmd.specs:
                    for entity in entities:
                        eid = entity.get("id") or entity.get("entity_id") or entity.get("name")
                        if eid == spec.new_id:
                            self._create_entity_internal(entity)
                            break


# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------


class TestAltDragDuplicateFlow:
    """Integration tests for alt-drag duplicate flow."""

    def test_begin_creates_duplicates(self) -> None:
        """Begin should create duplicated entities in scene."""
        scene = make_minimal_scene()
        controller = FakeEditorController(scene)

        # Set selection
        controller._selected_entity_ids = ["entity_a", "entity_b"]
        controller._primary_entity_id = "entity_a"
        controller.selected_entity = controller._get_sprite_for_entity_id("entity_a")

        # Begin alt-drag duplicate
        controller.begin_alt_drag_duplicate(0.0, 0.0)

        # Verify state
        assert controller._alt_dup_active is True
        assert controller._alt_dup_specs is not None
        assert len(controller._alt_dup_specs) == 2

        # Verify new entities exist
        sc = controller.window.scene_controller
        entity_ids = [
            e.get("id") for e in sc._loaded_scene_data.get("entities", [])
        ]
        assert "entity_a_copy_1" in entity_ids
        assert "entity_b_copy_1" in entity_ids

        # Verify selection changed to copies
        assert controller._selected_entity_ids == ["entity_a_copy_1", "entity_b_copy_1"]

    def test_update_moves_duplicates(self) -> None:
        """Update should move duplicated entities."""
        scene = make_minimal_scene()
        controller = FakeEditorController(scene)
        controller.snap_enabled = False  # Disable snapping for precise test

        controller._selected_entity_ids = ["entity_a", "entity_b"]
        controller._primary_entity_id = "entity_a"
        controller.begin_alt_drag_duplicate(0.0, 0.0)

        # Move to (50, 25)
        controller.update_alt_drag_duplicate(50.0, 25.0)

        # Check positions
        copy_a = controller._get_sprite_for_entity_id("entity_a_copy_1")
        copy_b = controller._get_sprite_for_entity_id("entity_b_copy_1")

        assert copy_a is not None
        assert copy_b is not None
        # entity_a was at (0, 0), moved by (50, 25)
        assert copy_a.center_x == 50.0
        assert copy_a.center_y == 25.0
        # entity_b was at (100, 100), moved by (50, 25)
        assert copy_b.center_x == 150.0
        assert copy_b.center_y == 125.0

        # Originals should be unchanged
        orig_a = controller._get_sprite_for_entity_id("entity_a")
        orig_b = controller._get_sprite_for_entity_id("entity_b")
        assert orig_a.center_x == 0.0
        assert orig_b.center_x == 100.0

    def test_end_commits_single_undo_command(self) -> None:
        """End should push exactly one undo command."""
        scene = make_minimal_scene()
        controller = FakeEditorController(scene)
        controller.snap_enabled = False

        controller._selected_entity_ids = ["entity_a"]
        controller._primary_entity_id = "entity_a"
        controller.begin_alt_drag_duplicate(0.0, 0.0)
        controller.update_alt_drag_duplicate(100.0, 100.0)

        initial_undo_count = len(controller.undo_stack)
        controller.end_alt_drag_duplicate()

        # Should have exactly one new command
        assert len(controller.undo_stack) == initial_undo_count + 1
        assert controller.undo_stack[-1]["type"] == "AltDragDuplicate"

        # State should be reset
        assert controller._alt_dup_active is False

    def test_cancel_removes_duplicates(self) -> None:
        """Cancel should remove duplicated entities."""
        scene = make_minimal_scene()
        controller = FakeEditorController(scene)

        controller._selected_entity_ids = ["entity_a"]
        controller._primary_entity_id = "entity_a"
        controller.begin_alt_drag_duplicate(0.0, 0.0)

        # Verify copy exists
        sc = controller.window.scene_controller
        entity_ids_before = [e.get("id") for e in sc._loaded_scene_data.get("entities", [])]
        assert "entity_a_copy_1" in entity_ids_before

        # Cancel
        controller.cancel_alt_drag_duplicate()

        # Verify copy removed
        entity_ids_after = [e.get("id") for e in sc._loaded_scene_data.get("entities", [])]
        assert "entity_a_copy_1" not in entity_ids_after
        assert "entity_a" in entity_ids_after

        # Selection should be restored
        assert controller._selected_entity_ids == ["entity_a"]
        assert controller._alt_dup_active is False

    def test_undo_removes_duplicates(self) -> None:
        """Undo should remove duplicated entities."""
        scene = make_minimal_scene()
        controller = FakeEditorController(scene)
        controller.snap_enabled = False

        controller._selected_entity_ids = ["entity_a"]
        controller._primary_entity_id = "entity_a"
        controller.begin_alt_drag_duplicate(0.0, 0.0)
        controller.update_alt_drag_duplicate(50.0, 50.0)
        controller.end_alt_drag_duplicate()

        # Verify copy exists
        sc = controller.window.scene_controller
        entity_ids_before = [e.get("id") for e in sc._loaded_scene_data.get("entities", [])]
        assert "entity_a_copy_1" in entity_ids_before

        # Undo
        controller.undo()

        # Verify copy removed
        entity_ids_after = [e.get("id") for e in sc._loaded_scene_data.get("entities", [])]
        assert "entity_a_copy_1" not in entity_ids_after

    def test_redo_restores_duplicates(self) -> None:
        """Redo should restore duplicated entities at final positions."""
        scene = make_minimal_scene()
        controller = FakeEditorController(scene)
        controller.snap_enabled = False

        controller._selected_entity_ids = ["entity_a"]
        controller._primary_entity_id = "entity_a"
        controller.begin_alt_drag_duplicate(0.0, 0.0)
        controller.update_alt_drag_duplicate(75.0, 75.0)
        controller.end_alt_drag_duplicate()

        # Undo
        controller.undo()

        # Redo
        controller.redo()

        # Verify copy restored
        sc = controller.window.scene_controller
        entity_ids = [e.get("id") for e in sc._loaded_scene_data.get("entities", [])]
        assert "entity_a_copy_1" in entity_ids

        # Check position is at final position
        copy_entity = next(
            e for e in sc._loaded_scene_data.get("entities", [])
            if e.get("id") == "entity_a_copy_1"
        )
        assert copy_entity["x"] == 75.0
        assert copy_entity["y"] == 75.0

    def test_snapping_affects_only_pivot(self) -> None:
        """Snapping should only affect pivot position, delta applied to all."""
        scene = make_minimal_scene()
        controller = FakeEditorController(scene)
        controller.snap_enabled = True
        controller.snap_mode = "grid16"
        controller.grid_size = 16

        controller._selected_entity_ids = ["entity_a", "entity_b"]
        controller._primary_entity_id = "entity_a"
        controller.begin_alt_drag_duplicate(0.0, 0.0)

        # Move by (17, 17) - should snap to (16, 16) for pivot
        controller.update_alt_drag_duplicate(17.0, 17.0)

        copy_a = controller._get_sprite_for_entity_id("entity_a_copy_1")
        copy_b = controller._get_sprite_for_entity_id("entity_b_copy_1")

        # entity_a (pivot) was at (0, 0), moved to (16, 16) after snap
        assert copy_a.center_x == 16.0
        assert copy_a.center_y == 16.0

        # entity_b was at (100, 100), moved by snapped delta (16, 16)
        assert copy_b.center_x == 116.0
        assert copy_b.center_y == 116.0

    def test_deterministic_id_generation(self) -> None:
        """IDs should be deterministically generated."""
        scene = make_minimal_scene()
        controller1 = FakeEditorController(copy.deepcopy(scene))
        controller2 = FakeEditorController(copy.deepcopy(scene))

        # Same operations on both
        for controller in [controller1, controller2]:
            controller._selected_entity_ids = ["entity_a", "entity_b"]
            controller._primary_entity_id = "entity_a"
            controller.begin_alt_drag_duplicate(0.0, 0.0)

        # Should have same IDs
        ids1 = [spec.new_id for spec in controller1._alt_dup_specs]
        ids2 = [spec.new_id for spec in controller2._alt_dup_specs]
        assert ids1 == ids2

    def test_multiselect_preserves_relative_positions(self) -> None:
        """Multi-selection should preserve relative positions between entities."""
        scene = make_minimal_scene()
        controller = FakeEditorController(scene)
        controller.snap_enabled = False

        controller._selected_entity_ids = ["entity_a", "entity_b"]
        controller._primary_entity_id = "entity_a"
        controller.begin_alt_drag_duplicate(0.0, 0.0)
        controller.update_alt_drag_duplicate(200.0, 200.0)
        controller.end_alt_drag_duplicate()

        copy_a = controller._get_sprite_for_entity_id("entity_a_copy_1")
        copy_b = controller._get_sprite_for_entity_id("entity_b_copy_1")

        # Original relative position: entity_b is 100 units right and up from entity_a
        # After move, should maintain same relative position
        relative_x = copy_b.center_x - copy_a.center_x
        relative_y = copy_b.center_y - copy_a.center_y
        assert relative_x == 100.0
        assert relative_y == 100.0


class TestAltDragDuplicateRightClickCancel:
    """Tests for right-click cancel during alt-drag duplicate."""

    def test_right_click_cancels_alt_dup(self) -> None:
        """Right-click during alt-dup should cancel and remove duplicates."""
        from unittest.mock import patch
        from engine import arcade_fallback as arcade_stub

        scene = make_minimal_scene()
        controller = FakeEditorController(scene)

        # Set selection
        controller._selected_entity_ids = ["entity_a"]
        controller._primary_entity_id = "entity_a"
        controller.selected_entity = controller._get_sprite_for_entity_id("entity_a")

        # Begin alt-drag duplicate
        controller.begin_alt_drag_duplicate(0.0, 0.0)

        # Verify alt-dup is active and copy exists
        assert controller._alt_dup_active is True
        sc = controller.window.scene_controller
        entity_ids_before = [e.get("id") for e in sc._loaded_scene_data.get("entities", [])]
        assert "entity_a_copy_1" in entity_ids_before

        # Simulate right-click through input handler
        with patch("engine.optional_arcade.arcade", arcade_stub):
            from engine.editor_runtime.input import handle_mouse_click

            # Set up controller for input handler
            controller.shape_edit_mode = False
            controller.tile_panel_active = False
            controller.asset_place_active = False
            controller.palette_active = False
            controller.occluder_tool_active = False
            controller.lights_tool_active = False
            controller.tool_mode = "SELECT"
            controller._context_menu_open = False

            # Screen coords (will be converted to world internally)
            controller.window.screen_to_world = lambda x, y: (x, y)

            result = handle_mouse_click(
                controller, 100.0, 100.0, arcade_stub.MOUSE_BUTTON_RIGHT, 0
            )

        # RMB should be consumed
        assert result is True

        # Alt-dup should be cancelled
        assert controller._alt_dup_active is False

        # Duplicate should be removed
        entity_ids_after = [e.get("id") for e in sc._loaded_scene_data.get("entities", [])]
        assert "entity_a_copy_1" not in entity_ids_after

        # Original should still exist
        assert "entity_a" in entity_ids_after

        # Selection should be restored to original
        assert controller._selected_entity_ids == ["entity_a"]

    def test_right_click_does_not_push_undo_on_cancel(self) -> None:
        """Right-click cancel should not push an undo command."""
        from unittest.mock import patch
        from engine import arcade_fallback as arcade_stub

        scene = make_minimal_scene()
        controller = FakeEditorController(scene)

        controller._selected_entity_ids = ["entity_a"]
        controller._primary_entity_id = "entity_a"
        controller.selected_entity = controller._get_sprite_for_entity_id("entity_a")

        initial_undo_count = len(controller.undo_stack)

        controller.begin_alt_drag_duplicate(0.0, 0.0)

        # Simulate right-click
        with patch("engine.optional_arcade.arcade", arcade_stub):
            from engine.editor_runtime.input import handle_mouse_click

            controller.shape_edit_mode = False
            controller.tile_panel_active = False
            controller.asset_place_active = False
            controller.palette_active = False
            controller.occluder_tool_active = False
            controller.lights_tool_active = False
            controller.tool_mode = "SELECT"
            controller._context_menu_open = False
            controller.window.screen_to_world = lambda x, y: (x, y)

            handle_mouse_click(
                controller, 100.0, 100.0, arcade_stub.MOUSE_BUTTON_RIGHT, 0
            )

        # No undo command should have been pushed
        assert len(controller.undo_stack) == initial_undo_count

    def test_right_click_blocks_context_menu_during_alt_dup(self) -> None:
        """Right-click should not open context menu when alt-dup is active."""
        from unittest.mock import patch
        from engine import arcade_fallback as arcade_stub

        scene = make_minimal_scene()
        controller = FakeEditorController(scene)

        controller._selected_entity_ids = ["entity_a"]
        controller._primary_entity_id = "entity_a"
        controller.selected_entity = controller._get_sprite_for_entity_id("entity_a")
        controller._context_menu_open = False

        controller.begin_alt_drag_duplicate(0.0, 0.0)

        # Simulate right-click
        with patch("engine.optional_arcade.arcade", arcade_stub):
            from engine.editor_runtime.input import handle_mouse_click

            controller.shape_edit_mode = False
            controller.tile_panel_active = False
            controller.asset_place_active = False
            controller.palette_active = False
            controller.occluder_tool_active = False
            controller.lights_tool_active = False
            controller.tool_mode = "SELECT"
            controller.window.screen_to_world = lambda x, y: (x, y)

            handle_mouse_click(
                controller, 100.0, 100.0, arcade_stub.MOUSE_BUTTON_RIGHT, 0
            )

        # Context menu should NOT be open
        assert controller._context_menu_open is False

    def test_right_click_opens_context_menu_when_alt_dup_inactive(self) -> None:
        """Right-click should open context menu normally when alt-dup is NOT active."""
        from unittest.mock import patch
        from engine import arcade_fallback as arcade_stub

        scene = make_minimal_scene()
        controller = FakeEditorController(scene)

        controller._selected_entity_ids = ["entity_a"]
        controller._primary_entity_id = "entity_a"
        controller.selected_entity = controller._get_sprite_for_entity_id("entity_a")
        controller._context_menu_open = False
        controller._alt_dup_active = False  # Explicitly not active

        # Simulate right-click (no alt-dup active)
        with patch("engine.optional_arcade.arcade", arcade_stub):
            from engine.editor_runtime.input import handle_mouse_click

            controller.shape_edit_mode = False
            controller.tile_panel_active = False
            controller.asset_place_active = False
            controller.palette_active = False
            controller.occluder_tool_active = False
            controller.lights_tool_active = False
            controller.tool_mode = "SELECT"
            controller.window.screen_to_world = lambda x, y: (x, y)
            controller.window.width = 800
            controller.window.height = 600

            result = handle_mouse_click(
                controller, 100.0, 100.0, arcade_stub.MOUSE_BUTTON_RIGHT, 0
            )

        # RMB should be consumed
        assert result is True

        # Context menu SHOULD be open (normal behavior)
        assert controller._context_menu_open is True
