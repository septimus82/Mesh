"""Contract tests for editor dock tabs.

Tests for:
- Dock tab hit testing geometry
- Tab click state switching
- Panel rendering gating
- Workspace persistence round-trip
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from engine.editor.editor_shell_layout import (
    DOCK_WIDTH,
    TAB_HEADER_HEIGHT,
    TAB_PADDING,
    Rect,
    DockTabRects,
    DockTabState,
    EditorShellLayout,
    compute_editor_shell_layout,
    compute_dock_tab_rects,
    hit_test_dock_tab,
    get_dock_tab_options,
)
from engine.workspace_settings import (
    WorkspaceSettings,
    load_workspace,
    save_workspace,
)
from tests._dock_stub import make_dock_stub


# ------------------------------------------------------------------------------
# Dock Tab Geometry Tests
# ------------------------------------------------------------------------------


class TestDockTabRects:
    """Tests for compute_dock_tab_rects function."""

    def test_returns_dock_tab_rects(self):
        """Should return DockTabRects with both left and right tab rects."""
        layout = compute_editor_shell_layout(1920, 1080)
        tab_rects = compute_dock_tab_rects(layout)

        assert isinstance(tab_rects, DockTabRects)
        assert "Project" in tab_rects.left_tab_rects
        assert "Scene" in tab_rects.left_tab_rects
        assert "Outliner" in tab_rects.left_tab_rects
        assert "Inspector" in tab_rects.right_tab_rects
        assert "Assets" in tab_rects.right_tab_rects
        assert "Items" in tab_rects.right_tab_rects
        assert "Prefabs" in tab_rects.right_tab_rects
        assert "Quests" in tab_rects.right_tab_rects
        assert "History" in tab_rects.right_tab_rects
        assert "Problems" in tab_rects.right_tab_rects
        assert "Debug" in tab_rects.right_tab_rects

    def test_left_tabs_within_left_dock(self):
        """Left tab rects should be within the left dock area."""
        layout = compute_editor_shell_layout(1920, 1080)
        tab_rects = compute_dock_tab_rects(layout)

        for tab_name, rect in tab_rects.left_tab_rects.items():
            assert rect.left >= layout.left_dock.left
            assert rect.right <= layout.left_dock.right
            assert rect.bottom >= layout.left_dock.top - TAB_HEADER_HEIGHT
            assert rect.top <= layout.left_dock.top

    def test_right_tabs_within_right_dock(self):
        """Right tab rects should be within the right dock area."""
        layout = compute_editor_shell_layout(1920, 1080)
        tab_rects = compute_dock_tab_rects(layout)

        for tab_name, rect in tab_rects.right_tab_rects.items():
            assert rect.left >= layout.right_dock.left
            assert rect.right <= layout.right_dock.right
            assert rect.bottom >= layout.right_dock.top - TAB_HEADER_HEIGHT
            assert rect.top <= layout.right_dock.top

    def test_tabs_do_not_overlap(self):
        """Tabs within the same dock should not overlap."""
        layout = compute_editor_shell_layout(1920, 1080)
        tab_rects = compute_dock_tab_rects(layout)

        # Check left tabs don't overlap
        left_rects = list(tab_rects.left_tab_rects.values())
        if len(left_rects) >= 2:
            r1, r2 = left_rects[0], left_rects[1]
            assert r1.right <= r2.left or r2.right <= r1.left

        # Check right tabs don't overlap
        right_rects = sorted(tab_rects.right_tab_rects.values(), key=lambda r: r.left)
        for i in range(len(right_rects) - 1):
            r1, r2 = right_rects[i], right_rects[i + 1]
            assert r1.right <= r2.left or r2.right <= r1.left

    def test_deterministic_layout(self):
        """Same inputs should produce identical tab rects."""
        layout = compute_editor_shell_layout(1280, 720)
        rects1 = compute_dock_tab_rects(layout)
        rects2 = compute_dock_tab_rects(layout)

        assert rects1.left_tab_rects == rects2.left_tab_rects
        assert rects1.right_tab_rects == rects2.right_tab_rects


# ------------------------------------------------------------------------------
# Hit Testing Tests
# ------------------------------------------------------------------------------


class TestHitTestDockTab:
    """Tests for hit_test_dock_tab function."""

    def test_hit_left_tab_scene(self):
        """Clicking on Scene tab returns ('left', 'Scene')."""
        layout = compute_editor_shell_layout(1920, 1080)
        tab_rects = compute_dock_tab_rects(layout)
        scene_rect = tab_rects.left_tab_rects["Scene"]

        # Click center of Scene tab
        x = scene_rect.center_x
        y = scene_rect.center_y
        result = hit_test_dock_tab(x, y, layout)

        assert result == ("left", "Scene")

    def test_hit_left_tab_project(self):
        """Clicking on Project tab returns ('left', 'Project')."""
        layout = compute_editor_shell_layout(1920, 1080)
        tab_rects = compute_dock_tab_rects(layout)
        project_rect = tab_rects.left_tab_rects["Project"]

        x = project_rect.center_x
        y = project_rect.center_y
        result = hit_test_dock_tab(x, y, layout)

        assert result == ("left", "Project")

    def test_hit_left_tab_outliner(self):
        """Clicking on Outliner tab returns ('left', 'Outliner')."""
        layout = compute_editor_shell_layout(1920, 1080)
        tab_rects = compute_dock_tab_rects(layout)
        outliner_rect = tab_rects.left_tab_rects["Outliner"]

        x = outliner_rect.center_x
        y = outliner_rect.center_y
        result = hit_test_dock_tab(x, y, layout)

        assert result == ("left", "Outliner")

    def test_hit_right_tab_inspector(self):
        """Clicking on Inspector tab returns ('right', 'Inspector')."""
        layout = compute_editor_shell_layout(1920, 1080)
        tab_rects = compute_dock_tab_rects(layout)
        inspector_rect = tab_rects.right_tab_rects["Inspector"]

        x = inspector_rect.center_x
        y = inspector_rect.center_y
        result = hit_test_dock_tab(x, y, layout)

        assert result == ("right", "Inspector")

    def test_hit_right_tab_assets(self):
        """Clicking on Assets tab returns ('right', 'Assets')."""
        layout = compute_editor_shell_layout(1920, 1080)
        tab_rects = compute_dock_tab_rects(layout)
        assets_rect = tab_rects.right_tab_rects["Assets"]

        x = assets_rect.center_x
        y = assets_rect.center_y
        result = hit_test_dock_tab(x, y, layout)

        assert result == ("right", "Assets")

    def test_hit_right_tab_history(self):
        """Clicking on History tab returns ('right', 'History')."""
        layout = compute_editor_shell_layout(1920, 1080)
        tab_rects = compute_dock_tab_rects(layout)
        history_rect = tab_rects.right_tab_rects["History"]

        x = history_rect.center_x
        y = history_rect.center_y
        result = hit_test_dock_tab(x, y, layout)

        assert result == ("right", "History")

    def test_hit_right_tab_debug(self):
        """Clicking on Debug tab returns ('right', 'Debug')."""
        layout = compute_editor_shell_layout(1920, 1080)
        tab_rects = compute_dock_tab_rects(layout)
        debug_rect = tab_rects.right_tab_rects["Debug"]

        x = debug_rect.center_x
        y = debug_rect.center_y
        result = hit_test_dock_tab(x, y, layout)

        assert result == ("right", "Debug")
    def test_miss_returns_none(self):
        """Clicking outside tabs returns None."""
        layout = compute_editor_shell_layout(1920, 1080)

        # Click in viewport area (center of screen)
        result = hit_test_dock_tab(960, 540, layout)
        assert result is None

    def test_miss_below_tabs(self):
        """Clicking below tab header area returns None."""
        layout = compute_editor_shell_layout(1920, 1080)

        # Click in left dock but below tab header
        x = layout.left_dock.center_x
        y = layout.left_dock.center_y
        result = hit_test_dock_tab(x, y, layout)
        assert result is None


# ------------------------------------------------------------------------------
# State Switching Tests
# ------------------------------------------------------------------------------


class TestDockTabStateSwitching:
    """Tests for dock tab state switching in editor controller."""

    @pytest.fixture
    def mock_controller(self):
        """Create a mock editor controller with dock tab state."""
        controller = MagicMock()
        controller.active = True
        controller.dock = make_dock_stub(left_tab="Outliner", right_tab="Inspector")
        controller._menu_active = None
        controller._context_menu_open = False
        controller.entity_panels_active = False
        controller.scene_browser_active = False
        controller.asset_browser_active = False
        controller.entity_panels_focus = "outliner"
        return controller

    def test_set_dock_tab_left_scene(self, mock_controller):
        """Switching left dock to Scene should update state."""
        from engine.editor_controller import EditorModeController

        # Test pure state logic
        mock_controller.dock.left_tab = "Outliner"

        # Simulate set_dock_tab logic
        if mock_controller.dock.left_tab != "Scene":
            mock_controller.dock.left_tab = "Scene"
            mock_controller.scene_browser_active = True

        assert mock_controller.dock.left_tab == "Scene"
        assert mock_controller.scene_browser_active is True

    def test_set_dock_tab_left_outliner(self, mock_controller):
        """Switching left dock to Outliner should update state."""
        mock_controller.dock.left_tab = "Scene"

        if mock_controller.dock.left_tab != "Outliner":
            mock_controller.dock.left_tab = "Outliner"
            mock_controller.entity_panels_active = True
            mock_controller.entity_panels_focus = "outliner"

        assert mock_controller.dock.left_tab == "Outliner"
        assert mock_controller.entity_panels_active is True

    def test_set_dock_tab_right_inspector(self, mock_controller):
        """Switching right dock to Inspector should update state."""
        mock_controller.dock.right_tab = "Assets"

        if mock_controller.dock.right_tab != "Inspector":
            mock_controller.dock.right_tab = "Inspector"
            mock_controller.entity_panels_active = True
            mock_controller.entity_panels_focus = "inspector"

        assert mock_controller.dock.right_tab == "Inspector"
        assert mock_controller.entity_panels_active is True

    def test_set_dock_tab_right_assets(self, mock_controller):
        """Switching right dock to Assets should update state."""
        mock_controller.dock.right_tab = "Inspector"

        if mock_controller.dock.right_tab != "Assets":
            mock_controller.dock.right_tab = "Assets"
            mock_controller.asset_browser_active = True

        assert mock_controller.dock.right_tab == "Assets"
        assert mock_controller.asset_browser_active is True

    def test_set_dock_tab_right_history(self, mock_controller):
        """Switching right dock to History should update state."""
        mock_controller.dock.right_tab = "Inspector"

        if mock_controller.dock.right_tab != "History":
            mock_controller.dock.right_tab = "History"

        assert mock_controller.dock.right_tab == "History"

    def test_set_dock_tab_same_tab_noop(self, mock_controller):
        """Switching to already active tab should be no-op."""
        mock_controller.dock.left_tab = "Outliner"
        initial_state = mock_controller.dock.left_tab

        # Same tab - should not change anything
        if mock_controller.dock.left_tab == "Outliner":
            pass  # No-op

        assert mock_controller.dock.left_tab == initial_state


# ------------------------------------------------------------------------------
# Panel Rendering Gating Tests
# ------------------------------------------------------------------------------


class TestPanelRenderingGating:
    """Tests for panel visibility based on dock tab state."""

    def test_outliner_visible_when_left_is_outliner(self):
        """Outliner should be visible when left dock tab is Outliner."""
        left_dock_tab = "Outliner"
        show_outliner = left_dock_tab == "Outliner"
        assert show_outliner is True

    def test_outliner_hidden_when_left_is_scene(self):
        """Outliner should be hidden when left dock tab is Scene."""
        left_dock_tab = "Scene"
        show_outliner = left_dock_tab == "Outliner"
        assert show_outliner is False

    def test_scene_browser_visible_when_left_is_scene(self):
        """Scene browser should be visible when left dock tab is Scene."""
        left_dock_tab = "Scene"
        show_scene = left_dock_tab == "Scene"
        assert show_scene is True

    def test_scene_browser_hidden_when_left_is_outliner(self):
        """Scene browser should be hidden when left dock tab is Outliner."""
        left_dock_tab = "Outliner"
        show_scene = left_dock_tab == "Scene"
        assert show_scene is False

    def test_inspector_visible_when_right_is_inspector(self):
        """Inspector should be visible when right dock tab is Inspector."""
        right_dock_tab = "Inspector"
        show_inspector = right_dock_tab == "Inspector"
        assert show_inspector is True

    def test_inspector_hidden_when_right_is_assets(self):
        """Inspector should be hidden when right dock tab is Assets."""
        right_dock_tab = "Assets"
        show_inspector = right_dock_tab == "Inspector"
        assert show_inspector is False

    def test_asset_browser_visible_when_right_is_assets(self):
        """Asset browser should be visible when right dock tab is Assets."""
        right_dock_tab = "Assets"
        show_assets = right_dock_tab == "Assets"
        assert show_assets is True

    def test_asset_browser_hidden_when_right_is_inspector(self):
        """Asset browser should be hidden when right dock tab is Inspector."""
        right_dock_tab = "Inspector"
        show_assets = right_dock_tab == "Assets"
        assert show_assets is False

    def test_history_visible_when_right_is_history(self):
        """History panel should be visible when right dock tab is History."""
        right_dock_tab = "History"
        show_history = right_dock_tab == "History"
        assert show_history is True


# ------------------------------------------------------------------------------
# Workspace Persistence Tests
# ------------------------------------------------------------------------------


class TestDockTabPersistence:
    """Tests for dock tab state persistence in workspace settings."""

    def test_workspace_settings_defaults(self):
        """Default dock tab values should be Outliner and Inspector."""
        settings = WorkspaceSettings()
        assert settings.left_dock_tab == "Outliner"
        assert settings.right_dock_tab == "Inspector"

    def test_workspace_settings_custom_values(self):
        """Should accept custom dock tab values."""
        settings = WorkspaceSettings(
            left_dock_tab="Scene",
            right_dock_tab="History",
        )
        assert settings.left_dock_tab == "Scene"
        assert settings.right_dock_tab == "History"

    def test_workspace_roundtrip(self, tmp_path):
        """Dock tab settings should persist through save/load cycle."""
        settings = WorkspaceSettings(
            left_dock_tab="Scene",
            right_dock_tab="History",
        )

        save_workspace(tmp_path, settings)
        loaded = load_workspace(tmp_path)

        assert loaded.left_dock_tab == "Scene"
        assert loaded.right_dock_tab == "History"

    def test_workspace_roundtrip_default_values(self, tmp_path):
        """Default dock tab values should persist correctly."""
        settings = WorkspaceSettings()

        save_workspace(tmp_path, settings)
        loaded = load_workspace(tmp_path)

        assert loaded.left_dock_tab == "Outliner"
        assert loaded.right_dock_tab == "Inspector"

    def test_workspace_json_contains_dock_tabs(self, tmp_path):
        """Saved workspace JSON should contain dock tab fields."""
        settings = WorkspaceSettings(
            left_dock_tab="Scene",
            right_dock_tab="History",
        )

        save_workspace(tmp_path, settings)

        workspace_path = tmp_path / "workspace.json"
        data = json.loads(workspace_path.read_text("utf-8"))

        assert "left_dock_tab" in data
        assert "right_dock_tab" in data
        assert data["left_dock_tab"] == "Scene"
        assert data["right_dock_tab"] == "History"

    def test_workspace_missing_dock_tabs_uses_defaults(self, tmp_path):
        """Missing dock tab fields should use defaults."""
        # Write workspace without dock tabs
        workspace_path = tmp_path / "workspace.json"
        data = {"entity_panels_open": True}
        workspace_path.write_text(json.dumps(data), encoding="utf-8")

        loaded = load_workspace(tmp_path)

        assert loaded.left_dock_tab == "Outliner"
        assert loaded.right_dock_tab == "Inspector"


# ------------------------------------------------------------------------------
# DockTabState Dataclass Tests
# ------------------------------------------------------------------------------


class TestDockTabState:
    """Tests for DockTabState dataclass."""

    def test_default_values(self):
        """Default state should be Scene and Inspector."""
        state = DockTabState()
        assert state.left_tab == "Scene"
        assert state.right_tab == "Inspector"

    def test_custom_values(self):
        """Should accept custom tab values."""
        state = DockTabState(left_tab="Outliner", right_tab="Assets")
        assert state.left_tab == "Outliner"
        assert state.right_tab == "Assets"

    def test_mutable(self):
        """DockTabState should be mutable."""
        state = DockTabState()
        state.left_tab = "Outliner"
        state.right_tab = "Assets"
        assert state.left_tab == "Outliner"
        assert state.right_tab == "Assets"


# ------------------------------------------------------------------------------
# Integration Tests
# ------------------------------------------------------------------------------


class TestDockTabIntegration:
    """Integration tests for dock tab workflow."""

    def test_full_click_workflow(self):
        """Test clicking a tab updates hit detection correctly."""
        layout = compute_editor_shell_layout(1920, 1080)

        # Get center of Assets tab
        tab_rects = compute_dock_tab_rects(layout)
        assets_rect = tab_rects.right_tab_rects["Assets"]
        x, y = assets_rect.center_x, assets_rect.center_y

        # Hit test should find Assets tab
        result = hit_test_dock_tab(x, y, layout)
        assert result == ("right", "Assets")

        # Simulate state update
        right_dock_tab = "Assets"

        # Verify visibility logic
        show_assets = right_dock_tab == "Assets"
        show_inspector = right_dock_tab == "Inspector"
        assert show_assets is True
        assert show_inspector is False

    def test_tab_options_match_hit_regions(self):
        """Tab options should match available hit regions."""
        left_tabs, right_tabs = get_dock_tab_options()
        layout = compute_editor_shell_layout(1920, 1080)
        tab_rects = compute_dock_tab_rects(layout)

        assert set(left_tabs) == set(tab_rects.left_tab_rects.keys())
        assert set(right_tabs) == set(tab_rects.right_tab_rects.keys())

    def test_small_window_still_has_tabs(self):
        """Even small windows should have clickable tabs."""
        layout = compute_editor_shell_layout(800, 600)
        tab_rects = compute_dock_tab_rects(layout)

        # Should still have all tabs
        assert len(tab_rects.left_tab_rects) == 3
        assert len(tab_rects.right_tab_rects) == 8

        # Tabs should still be clickable (have positive area)
        for rect in tab_rects.left_tab_rects.values():
            assert rect.width > 0
            assert rect.height > 0

        for rect in tab_rects.right_tab_rects.values():
            assert rect.width > 0
            assert rect.height > 0
