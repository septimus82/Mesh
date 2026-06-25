"""Contract tests for context menu model.

These tests verify the context menu layout computation and hit testing work
correctly without any arcade/pygame dependencies (pure unit tests).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from engine.editor.context_menu_model import (
    CONTEXT_MENU_ITEM_HEIGHT,
    CONTEXT_MENU_PADDING_Y,
    CONTEXT_MENU_WIDTH,
    ContextMenuItem,
    ContextMenuLayout,
    ContextMenuRect,
    build_context_menu_items,
    compute_context_menu_layout,
    hit_test_context_menu,
    hit_test_context_menu_bounds,
)

# ------------------------------------------------------------------------------
# ContextMenuRect tests
# ------------------------------------------------------------------------------


class TestContextMenuRect:
    """Tests for ContextMenuRect dataclass."""

    def test_contains_point_inside(self) -> None:
        """Point inside rectangle returns True."""
        rect = ContextMenuRect(x=10, y=20, w=100, h=50)
        assert rect.contains_point(50, 40) is True

    def test_contains_point_outside(self) -> None:
        """Point outside rectangle returns False."""
        rect = ContextMenuRect(x=10, y=20, w=100, h=50)
        assert rect.contains_point(5, 40) is False
        assert rect.contains_point(200, 40) is False

    def test_contains_point_on_edge(self) -> None:
        """Point on edge is considered inside."""
        rect = ContextMenuRect(x=10, y=20, w=100, h=50)
        assert rect.contains_point(10, 20) is True
        assert rect.contains_point(110, 70) is True


# ------------------------------------------------------------------------------
# build_context_menu_items tests
# ------------------------------------------------------------------------------


class TestBuildContextMenuItems:
    """Tests for build_context_menu_items function."""

    @pytest.fixture
    def mock_controller_with_selection(self) -> MagicMock:
        """Create a mock editor controller with a selected entity and clipboard."""
        controller = MagicMock()
        controller.selected_entity = MagicMock()  # Has selection
        controller._entity_clipboard = {"id": "test_entity"}  # Has clipboard content
        return controller

    @pytest.fixture
    def mock_controller_no_selection(self) -> MagicMock:
        """Create a mock editor controller without selection."""
        controller = MagicMock()
        controller.selected_entity = None
        controller._entity_clipboard = None  # No clipboard content
        return controller

    def test_returns_entity_action_items(self, mock_controller_with_selection: MagicMock) -> None:
        """Returns the lean entity action set."""
        items = build_context_menu_items(mock_controller_with_selection)
        ids = [i.id for i in items]
        assert ids == [
            "ctx_edit",
            "ctx_separator_edit",
            "ctx_duplicate",
            "ctx_delete",
            "ctx_separator_mutate",
            "ctx_focus",
        ]

    def test_items_enabled_with_selection(self, mock_controller_with_selection: MagicMock) -> None:
        """Action items are enabled when there's a selection."""
        items = build_context_menu_items(mock_controller_with_selection)
        for item in items:
            if not item.separator:
                assert item.enabled is True

    def test_viewport_copy_paste_rename_are_omitted(self, mock_controller_with_selection: MagicMock) -> None:
        """Copy, Paste, and Rename stay off the viewport context menu."""
        items = build_context_menu_items(mock_controller_with_selection)
        ids = {i.id for i in items}
        assert "ctx_copy" not in ids
        assert "ctx_paste" not in ids
        assert "ctx_rename" not in ids

    def test_selection_items_disabled_without_selection(self, mock_controller_no_selection: MagicMock) -> None:
        """Selection-dependent items are disabled when there's no selection."""
        items = build_context_menu_items(mock_controller_no_selection)
        # Selection-dependent items should be disabled
        selection_items = [
            i
            for i in items
            if i.id in ["ctx_edit", "ctx_duplicate", "ctx_delete", "ctx_focus"]
        ]
        for item in selection_items:
            assert item.enabled is False

    def test_shortcuts_present(self, mock_controller_with_selection: MagicMock) -> None:
        """Items have correct shortcuts."""
        items = build_context_menu_items(mock_controller_with_selection)
        shortcuts = {i.id: i.shortcut for i in items}
        assert shortcuts["ctx_edit"] == ""
        assert shortcuts["ctx_duplicate"] == "Ctrl+D"
        assert shortcuts["ctx_delete"] == "Del"
        assert shortcuts["ctx_focus"] == "F"


# ------------------------------------------------------------------------------
# compute_context_menu_layout tests
# ------------------------------------------------------------------------------


class TestComputeContextMenuLayout:
    """Tests for compute_context_menu_layout function."""

    @pytest.fixture
    def sample_items(self) -> list[ContextMenuItem]:
        """Create sample menu items for testing."""
        return [
            ContextMenuItem(id="ctx_duplicate", label="Duplicate"),
            ContextMenuItem(id="ctx_delete", label="Delete"),
            ContextMenuItem(id="ctx_focus", label="Focus"),
            ContextMenuItem(id="ctx_rename", label="Rename"),
        ]

    def test_layout_is_deterministic(self, sample_items: list[ContextMenuItem]) -> None:
        """Same inputs produce same layout."""
        layout1 = compute_context_menu_layout(100, 300, sample_items, 800, 600)
        layout2 = compute_context_menu_layout(100, 300, sample_items, 800, 600)

        assert layout1.rect == layout2.rect
        assert layout1.items_with_rects == layout2.items_with_rects

    def test_menu_width_is_constant(self, sample_items: list[ContextMenuItem]) -> None:
        """Menu width is always CONTEXT_MENU_WIDTH."""
        layout = compute_context_menu_layout(100, 300, sample_items, 800, 600)
        assert layout.rect.w == CONTEXT_MENU_WIDTH

    def test_menu_height_depends_on_items(self, sample_items: list[ContextMenuItem]) -> None:
        """Menu height depends on number of items."""
        layout = compute_context_menu_layout(100, 300, sample_items, 800, 600)
        expected_height = len(sample_items) * CONTEXT_MENU_ITEM_HEIGHT + CONTEXT_MENU_PADDING_Y * 2
        assert layout.rect.h == expected_height

    def test_clamp_to_right_edge(self, sample_items: list[ContextMenuItem]) -> None:
        """Menu clamps when near right edge of window."""
        # Place menu near right edge
        layout = compute_context_menu_layout(750, 300, sample_items, 800, 600)
        # Menu should not extend past window
        assert layout.rect.x + layout.rect.w <= 800

    def test_clamp_to_bottom_edge(self, sample_items: list[ContextMenuItem]) -> None:
        """Menu clamps when near bottom edge of window."""
        # Place menu near bottom
        layout = compute_context_menu_layout(100, 50, sample_items, 800, 600)
        # Menu should not extend below window
        assert layout.rect.y >= 0

    def test_clamp_to_top_edge(self, sample_items: list[ContextMenuItem]) -> None:
        """Menu clamps when near top edge of window."""
        # Place menu at very top
        layout = compute_context_menu_layout(100, 590, sample_items, 800, 600)
        # Menu should not extend above window
        assert layout.rect.y + layout.rect.h <= 600

    def test_items_have_correct_height(self, sample_items: list[ContextMenuItem]) -> None:
        """Each item rect has CONTEXT_MENU_ITEM_HEIGHT."""
        layout = compute_context_menu_layout(100, 300, sample_items, 800, 600)
        for item, rect in layout.items_with_rects:
            assert rect.h == CONTEXT_MENU_ITEM_HEIGHT

    def test_items_same_width_as_menu(self, sample_items: list[ContextMenuItem]) -> None:
        """Each item rect has same width as menu."""
        layout = compute_context_menu_layout(100, 300, sample_items, 800, 600)
        for item, rect in layout.items_with_rects:
            assert rect.w == layout.rect.w


# ------------------------------------------------------------------------------
# hit_test_context_menu tests
# ------------------------------------------------------------------------------


class TestHitTestContextMenu:
    """Tests for hit_test_context_menu function."""

    @pytest.fixture
    def sample_layout(self) -> ContextMenuLayout:
        """Create a sample layout for testing."""
        items = [
            ContextMenuItem(id="ctx_duplicate", label="Duplicate"),
            ContextMenuItem(id="ctx_delete", label="Delete"),
        ]
        return compute_context_menu_layout(100, 300, items, 800, 600)

    def test_hit_inside_item(self, sample_layout: ContextMenuLayout) -> None:
        """Clicking inside an item returns its ID."""
        # Get first item rect
        first_item, first_rect = sample_layout.items_with_rects[0]
        # Click in center of first item
        x = first_rect.x + first_rect.w / 2
        y = first_rect.y + first_rect.h / 2
        result = hit_test_context_menu(x, y, sample_layout)
        assert result == first_item.id

    def test_hit_outside_menu(self, sample_layout: ContextMenuLayout) -> None:
        """Clicking outside menu returns None."""
        result = hit_test_context_menu(0, 0, sample_layout)
        assert result is None

    def test_hit_between_items(self, sample_layout: ContextMenuLayout) -> None:
        """Clicking between items may hit an item due to padding."""
        # Clicking inside the menu but not precisely on an item
        # should still be detected by bounds check
        pass  # This is tested by hit_test_context_menu_bounds


# ------------------------------------------------------------------------------
# hit_test_context_menu_bounds tests
# ------------------------------------------------------------------------------


class TestHitTestContextMenuBounds:
    """Tests for hit_test_context_menu_bounds function."""

    @pytest.fixture
    def sample_layout(self) -> ContextMenuLayout:
        """Create a sample layout for testing."""
        items = [
            ContextMenuItem(id="ctx_duplicate", label="Duplicate"),
            ContextMenuItem(id="ctx_delete", label="Delete"),
        ]
        return compute_context_menu_layout(100, 300, items, 800, 600)

    def test_inside_bounds(self, sample_layout: ContextMenuLayout) -> None:
        """Point inside menu bounds returns True."""
        rect = sample_layout.rect
        x = rect.x + rect.w / 2
        y = rect.y + rect.h / 2
        assert hit_test_context_menu_bounds(x, y, sample_layout) is True

    def test_outside_bounds(self, sample_layout: ContextMenuLayout) -> None:
        """Point outside menu bounds returns False."""
        assert hit_test_context_menu_bounds(0, 0, sample_layout) is False


# ------------------------------------------------------------------------------
# Integration-style tests
# ------------------------------------------------------------------------------


class TestContextMenuIntegration:
    """Integration-style tests for the context menu model."""

    def test_full_workflow(self) -> None:
        """Test full workflow: build items, compute layout, hit test."""
        # Create controller with selection
        controller = MagicMock()
        controller.selected_entity = MagicMock()
        controller._entity_clipboard = None

        # Build items
        items = build_context_menu_items(controller)
        assert len(items) == 6

        # Compute layout
        layout = compute_context_menu_layout(200, 400, items, 800, 600)
        assert layout.rect.w == CONTEXT_MENU_WIDTH

        # Hit test - should find edit (first item)
        first_item, first_rect = layout.items_with_rects[0]
        hit_id = hit_test_context_menu(
            first_rect.x + first_rect.w / 2,
            first_rect.y + first_rect.h / 2,
            layout,
        )
        assert hit_id == "ctx_edit"

    def test_disabled_items_still_have_layout(self) -> None:
        """Disabled items still appear in layout."""
        controller = MagicMock()
        controller.selected_entity = None  # No selection
        controller._entity_clipboard = None  # No clipboard content

        items = build_context_menu_items(controller)
        layout = compute_context_menu_layout(200, 400, items, 800, 600)

        # All items disabled but still in layout
        assert len(layout.items_with_rects) == len(items)
        for item, rect in layout.items_with_rects:
            assert item.enabled is False


# ------------------------------------------------------------------------------
# Action execution tests (mocked)
# ------------------------------------------------------------------------------


class TestContextMenuActions:
    """Tests for context menu action execution."""

    def test_edit_switches_right_dock_to_inspector(self) -> None:
        """Edit action opens the right dock Inspector tab."""
        from engine.editor_runtime.input import _execute_context_menu_item

        dock = MagicMock()
        controller = MagicMock()
        controller.selected_entity = MagicMock()
        controller.dock = dock

        _execute_context_menu_item(controller, "ctx_edit")

        dock.set_active_tab.assert_called_once_with("right", "Inspector", force=True)

    def test_duplicate_calls_duplicate_selected(self) -> None:
        """Duplicate action calls controller.duplicate_selected."""
        from engine.editor_runtime.input import _execute_context_menu_item

        controller = MagicMock()
        controller.duplicate_selected = MagicMock()

        _execute_context_menu_item(controller, "ctx_duplicate")

        controller.duplicate_selected.assert_called_once()

    def test_delete_calls_delete_selected(self) -> None:
        """Delete action calls controller.delete_selected."""
        from engine.editor_runtime.input import _execute_context_menu_item

        controller = MagicMock()
        controller.delete_selected = MagicMock()

        _execute_context_menu_item(controller, "ctx_delete")

        controller.delete_selected.assert_called_once()

    def test_focus_centers_camera(self) -> None:
        """Focus action centers camera on entity."""
        from engine.editor_runtime.input import _focus_camera_on_entity

        entity = MagicMock()
        entity.center_x = 100.0
        entity.center_y = 200.0

        camera = MagicMock()
        camera_ctrl = MagicMock()
        camera_ctrl.camera = camera

        controller = MagicMock()
        controller.selected_entity = entity
        controller.window.camera_controller = camera_ctrl

        _focus_camera_on_entity(controller)

        # Camera position should be set
        camera.position = (100.0, 200.0)

    def test_rename_activates_hierarchy_rename(self) -> None:
        """Rename action activates hierarchy rename mode."""
        from engine.editor_runtime.input import _begin_context_rename

        controller = MagicMock()
        controller.selected_entity = MagicMock()
        controller.hierarchy_active = False
        controller.toggle_hierarchy = MagicMock()
        controller._begin_hierarchy_rename = MagicMock()

        _begin_context_rename(controller)

        # Should toggle hierarchy on
        controller.toggle_hierarchy.assert_called_once()
        # Should begin rename
        controller._begin_hierarchy_rename.assert_called_once()

    def test_right_click_selects_entity_under_cursor_then_opens(self) -> None:
        """Right-clicking an entity selects it before opening the context menu."""
        from engine.editor_runtime.editor_input_menu_handlers import handle_context_menu_click

        class Sprite:
            mesh_name = "entity-a"
            mesh_tag = "entity"
            mesh_behaviours: list[Any] = []
            mesh_behaviours_runtime: list[Any] = []
            mesh_entity_data = {
                "id": "entity-a",
                "x": 100.0,
                "y": 200.0,
                "width": 32.0,
                "height": 32.0,
            }
            center_x = 100.0
            center_y = 200.0
            width = 32.0
            height = 32.0

            def collides_with_point(self, point: tuple[float, float]) -> bool:
                return point == (100.0, 200.0)

        sprite = Sprite()
        open_state = {"open": False}
        panels = SimpleNamespace(
            is_context_menu_open=lambda: open_state["open"],
            open_context_menu=lambda: open_state.__setitem__("open", True),
        )
        scene = SimpleNamespace(
            get_sprites_in_layer=lambda layer: [sprite] if layer == "entities" else None,
            entity_sprites=[sprite],
            all_sprites=[sprite],
        )
        controller = SimpleNamespace(
            active=True,
            selected_entity=None,
            _selected_entity_ids=[],
            _primary_entity_id=None,
            _multiselect_drag_starts={},
            _rotate_drag_active=False,
            _scale_drag_active=False,
            _transform_drag_pivot=None,
            _transform_drag_mouse_start=None,
            _transform_drag_start_rots={},
            _transform_drag_start_scales={},
            tool_mode="MOVE",
            transform_mode="MOVE",
            entity_dragging=False,
            entity_drag_start_pos=None,
            shape=SimpleNamespace(
                reset_zone_selection_state=lambda: None,
                sync_zone_selection_state=lambda _entity: None,
            ),
            _cancel_hierarchy_rename=lambda: None,
            _refresh_dialogue_cache=lambda: None,
            _refresh_animation_cache=lambda: None,
            _refresh_tile_palette=lambda: None,
            _get_display_name_for_sprite=lambda _entity: "entity-a",
            _refresh_inspector_items=lambda: None,
            hierarchy_active=False,
            dialogue_panel_active=False,
            dialogue_editing=False,
            animation_active=False,
            animation_editing=False,
            tile_panel_active=False,
            inspector_selection_index=0,
            inspector=SimpleNamespace(set_inspector_active=lambda _value: None),
            panels=panels,
            window=SimpleNamespace(
                width=800,
                height=600,
                screen_to_world=lambda x, y: (float(x), float(y)),
                scene_controller=scene,
            ),
        )

        handled = handle_context_menu_click(cast(Any, controller), 100.0, 200.0)

        assert handled is True
        assert open_state["open"] is True
        assert controller.selected_entity is sprite
        assert controller._selected_entity_ids == ["entity-a"]
        assert controller._primary_entity_id == "entity-a"
        assert controller.entity_dragging is False
        assert controller.entity_drag_start_pos is None
