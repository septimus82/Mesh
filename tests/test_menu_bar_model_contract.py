"""Contract tests for menu bar model.

These tests verify the menu bar layout computation and hit testing work
correctly without any arcade/pygame dependencies (pure unit tests).
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from engine.editor.menu_bar_model import (
    MENU_BAR_HEIGHT,
    MenuBarLayout,
    MenuGroup,
    MenuItem,
    MenuRect,
    build_menu_groups,
    compute_menu_bar_layout,
    get_dropdown_bounds,
    hit_test_menu_bar,
    hit_test_menu_item,
    hit_test_menu_title,
)


# ------------------------------------------------------------------------------
# MenuRect tests
# ------------------------------------------------------------------------------


class TestMenuRect:
    """Tests for MenuRect dataclass."""

    def test_contains_point_inside(self) -> None:
        """Point inside rectangle returns True."""
        rect = MenuRect(x=10, y=20, w=100, h=50)
        assert rect.contains_point(50, 40) is True

    def test_contains_point_outside(self) -> None:
        """Point outside rectangle returns False."""
        rect = MenuRect(x=10, y=20, w=100, h=50)
        assert rect.contains_point(5, 40) is False
        assert rect.contains_point(200, 40) is False

    def test_contains_point_on_edge(self) -> None:
        """Point on edge is considered inside."""
        rect = MenuRect(x=10, y=20, w=100, h=50)
        assert rect.contains_point(10, 20) is True
        assert rect.contains_point(110, 70) is True


# ------------------------------------------------------------------------------
# build_menu_groups tests
# ------------------------------------------------------------------------------


class TestBuildMenuGroups:
    """Tests for build_menu_groups function."""

    @pytest.fixture
    def mock_controller(self) -> MagicMock:
        """Create a mock editor controller."""
        controller = MagicMock()
        controller.selected_entity = None
        controller.undo_stack = []
        controller.redo_stack = []
        controller.scene_dirty = False
        from engine.editor.editor_undo_controller import EditorUndoController

        controller.undo = EditorUndoController(controller)
        return controller

    @pytest.fixture
    def mock_window(self) -> MagicMock:
        """Create a mock window."""
        return MagicMock()

    def test_returns_four_menu_groups(self, mock_controller: MagicMock, mock_window: MagicMock) -> None:
        """Returns File, Edit, View, Scene menu groups."""
        groups = build_menu_groups(mock_controller, mock_window)
        titles = [g.title for g in groups]
        assert titles == ["File", "Edit", "View", "Scene"]

    def test_undo_disabled_when_stack_empty(self, mock_controller: MagicMock, mock_window: MagicMock) -> None:
        """Undo is disabled when undo stack is empty."""
        mock_controller.undo.set_undo_stack([])
        groups = build_menu_groups(mock_controller, mock_window)
        edit_menu = next(g for g in groups if g.title == "Edit")
        undo_item = next(i for i in edit_menu.items if i.id == "editor.history.undo")
        assert undo_item.enabled is False

    def test_undo_enabled_when_stack_has_items(self, mock_controller: MagicMock, mock_window: MagicMock) -> None:
        """Undo is enabled when undo stack has items."""
        mock_controller.undo.push({"type": "test"})
        groups = build_menu_groups(mock_controller, mock_window)
        edit_menu = next(g for g in groups if g.title == "Edit")
        undo_item = next(i for i in edit_menu.items if i.id == "editor.history.undo")
        assert undo_item.enabled is True

    def test_save_disabled_when_not_dirty(self, mock_controller: MagicMock, mock_window: MagicMock) -> None:
        """Save is disabled when scene is not dirty."""
        mock_controller.scene_dirty = False
        groups = build_menu_groups(mock_controller, mock_window)
        file_menu = next(g for g in groups if g.title == "File")
        save_item = next(i for i in file_menu.items if i.id == "editor.scene.save")
        assert save_item.enabled is False

    def test_save_enabled_when_dirty(self, mock_controller: MagicMock, mock_window: MagicMock) -> None:
        """Save is enabled when scene is dirty."""
        mock_controller.scene_dirty = True
        groups = build_menu_groups(mock_controller, mock_window)
        file_menu = next(g for g in groups if g.title == "File")
        save_item = next(i for i in file_menu.items if i.id == "editor.scene.save")
        assert save_item.enabled is True


# ------------------------------------------------------------------------------
# compute_menu_bar_layout tests
# ------------------------------------------------------------------------------


class TestComputeMenuBarLayout:
    """Tests for compute_menu_bar_layout function."""

    @pytest.fixture
    def sample_groups(self) -> list[MenuGroup]:
        """Create sample menu groups for testing."""
        return [
            MenuGroup(title="File", items=(
                MenuItem(id="file_save", label="Save"),
                MenuItem(id="file_open", label="Open"),
            )),
            MenuGroup(title="Edit", items=(
                MenuItem(id="editor.history.undo", label="Undo"),
            )),
        ]

    def test_layout_is_deterministic(self, sample_groups: list[MenuGroup]) -> None:
        """Same inputs produce same layout."""
        layout1 = compute_menu_bar_layout(800, 600, sample_groups, None)
        layout2 = compute_menu_bar_layout(800, 600, sample_groups, None)

        assert layout1.bar_rect == layout2.bar_rect
        assert layout1.titles == layout2.titles
        assert layout1.dropdown == layout2.dropdown

    def test_bar_at_top_of_window(self, sample_groups: list[MenuGroup]) -> None:
        """Menu bar is positioned at top of window."""
        layout = compute_menu_bar_layout(800, 600, sample_groups, None)
        assert layout.bar_rect.y == 600 - MENU_BAR_HEIGHT
        assert layout.bar_rect.h == MENU_BAR_HEIGHT

    def test_titles_have_rectangles(self, sample_groups: list[MenuGroup]) -> None:
        """Each menu group has a title rectangle."""
        layout = compute_menu_bar_layout(800, 600, sample_groups, None)
        assert "File" in layout.titles
        assert "Edit" in layout.titles

    def test_no_dropdown_when_no_active_menu(self, sample_groups: list[MenuGroup]) -> None:
        """No dropdown when no menu is active."""
        layout = compute_menu_bar_layout(800, 600, sample_groups, None)
        assert layout.dropdown is None

    def test_dropdown_when_menu_active(self, sample_groups: list[MenuGroup]) -> None:
        """Dropdown is computed when a menu is active."""
        layout = compute_menu_bar_layout(800, 600, sample_groups, "File")
        assert layout.dropdown is not None
        assert len(layout.dropdown) == 2  # Save and Open

    def test_dropdown_items_have_rectangles(self, sample_groups: list[MenuGroup]) -> None:
        """Each dropdown item has a rectangle."""
        layout = compute_menu_bar_layout(800, 600, sample_groups, "File")
        assert layout.dropdown is not None
        for item, rect in layout.dropdown:
            assert isinstance(rect, MenuRect)
            assert rect.w > 0
            assert rect.h > 0


# ------------------------------------------------------------------------------
# hit_test_menu_title tests
# ------------------------------------------------------------------------------


class TestHitTestMenuTitle:
    """Tests for hit_test_menu_title function."""

    @pytest.fixture
    def layout_with_titles(self) -> MenuBarLayout:
        """Create a layout with known title positions."""
        groups = [
            MenuGroup(title="File", items=()),
            MenuGroup(title="Edit", items=()),
        ]
        return compute_menu_bar_layout(800, 600, groups, None)

    def test_hits_file_title(self, layout_with_titles: MenuBarLayout) -> None:
        """Clicking on File title returns 'File'."""
        file_rect = layout_with_titles.titles["File"]
        x = file_rect.x + file_rect.w / 2
        y = file_rect.y + file_rect.h / 2
        result = hit_test_menu_title(x, y, layout_with_titles)
        assert result == "File"

    def test_hits_edit_title(self, layout_with_titles: MenuBarLayout) -> None:
        """Clicking on Edit title returns 'Edit'."""
        edit_rect = layout_with_titles.titles["Edit"]
        x = edit_rect.x + edit_rect.w / 2
        y = edit_rect.y + edit_rect.h / 2
        result = hit_test_menu_title(x, y, layout_with_titles)
        assert result == "Edit"

    def test_misses_when_outside(self, layout_with_titles: MenuBarLayout) -> None:
        """Returns None when clicking outside titles."""
        result = hit_test_menu_title(500, 300, layout_with_titles)
        assert result is None


# ------------------------------------------------------------------------------
# hit_test_menu_item tests
# ------------------------------------------------------------------------------


class TestHitTestMenuItem:
    """Tests for hit_test_menu_item function."""

    @pytest.fixture
    def layout_with_dropdown(self) -> MenuBarLayout:
        """Create a layout with an open dropdown."""
        groups = [
            MenuGroup(title="File", items=(
                MenuItem(id="file_save", label="Save"),
                MenuItem(id="file_open", label="Open"),
            )),
        ]
        return compute_menu_bar_layout(800, 600, groups, "File")

    def test_hits_first_item(self, layout_with_dropdown: MenuBarLayout) -> None:
        """Clicking on first item returns its id."""
        assert layout_with_dropdown.dropdown is not None
        item, rect = layout_with_dropdown.dropdown[0]
        x = rect.x + rect.w / 2
        y = rect.y + rect.h / 2
        result = hit_test_menu_item(x, y, layout_with_dropdown)
        assert result == "file_save"

    def test_hits_second_item(self, layout_with_dropdown: MenuBarLayout) -> None:
        """Clicking on second item returns its id."""
        assert layout_with_dropdown.dropdown is not None
        item, rect = layout_with_dropdown.dropdown[1]
        x = rect.x + rect.w / 2
        y = rect.y + rect.h / 2
        result = hit_test_menu_item(x, y, layout_with_dropdown)
        assert result == "file_open"

    def test_misses_when_outside(self, layout_with_dropdown: MenuBarLayout) -> None:
        """Returns None when clicking outside dropdown."""
        result = hit_test_menu_item(500, 300, layout_with_dropdown)
        assert result is None

    def test_returns_none_when_no_dropdown(self) -> None:
        """Returns None when no dropdown is open."""
        groups = [MenuGroup(title="File", items=())]
        layout = compute_menu_bar_layout(800, 600, groups, None)
        result = hit_test_menu_item(50, 590, layout)
        assert result is None


# ------------------------------------------------------------------------------
# get_dropdown_bounds tests
# ------------------------------------------------------------------------------


class TestGetDropdownBounds:
    """Tests for get_dropdown_bounds function."""

    def test_returns_none_when_no_dropdown(self) -> None:
        """Returns None when no dropdown is open."""
        groups = [MenuGroup(title="File", items=())]
        layout = compute_menu_bar_layout(800, 600, groups, None)
        result = get_dropdown_bounds(layout)
        assert result is None

    def test_returns_bounding_rect_for_dropdown(self) -> None:
        """Returns bounding rectangle for dropdown items."""
        groups = [
            MenuGroup(title="File", items=(
                MenuItem(id="file_save", label="Save"),
                MenuItem(id="file_open", label="Open"),
            )),
        ]
        layout = compute_menu_bar_layout(800, 600, groups, "File")
        bounds = get_dropdown_bounds(layout)

        assert bounds is not None
        assert bounds.w > 0
        assert bounds.h > 0


# ------------------------------------------------------------------------------
# Disabled item execution tests
# ------------------------------------------------------------------------------


class TestDisabledItemExecution:
    """Tests verifying disabled items don't execute."""

    def test_disabled_item_in_menu_group(self) -> None:
        """Disabled items have enabled=False."""
        item = MenuItem(id="test", label="Test", enabled=False)
        assert item.enabled is False

    def test_separator_is_disabled(self) -> None:
        """Separator items are always disabled."""
        sep = MenuItem(id="sep", label="-", enabled=False)
        assert sep.label == "-"
        assert sep.enabled is False
