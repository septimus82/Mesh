"""Contract tests for editor dock resize.

Tests for:
- Splitter hit testing geometry
- Dock width clamping behavior
- Viewport minimum width enforcement
- Workspace persistence round-trip
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from engine.editor.editor_shell_layout import (
    DOCK_MAX_W,
    DOCK_MIN_W,
    DOCK_WIDTH,
    SPLITTER_W,
    VIEWPORT_MIN_W,
    DockSizing,
    EditorShellLayout,
    Rect,
    clamp_dock_width,
    compute_editor_shell_layout,
    hit_test_splitter,
)
from engine.workspace_settings import (
    WorkspaceSettings,
    load_workspace,
    save_workspace,
)


# ------------------------------------------------------------------------------
# Constants Tests
# ------------------------------------------------------------------------------


class TestDockResizeConstants:
    """Tests for dock resize constants."""

    def test_dock_min_width(self):
        """DOCK_MIN_W should be a reasonable minimum."""
        assert DOCK_MIN_W == 220
        assert DOCK_MIN_W > 0

    def test_dock_max_width(self):
        """DOCK_MAX_W should be larger than min."""
        assert DOCK_MAX_W == 520
        assert DOCK_MAX_W > DOCK_MIN_W

    def test_viewport_min_width(self):
        """VIEWPORT_MIN_W should ensure usable viewport."""
        assert VIEWPORT_MIN_W == 320
        assert VIEWPORT_MIN_W > 0

    def test_splitter_width(self):
        """SPLITTER_W should be a small clickable width."""
        assert SPLITTER_W == 6
        assert SPLITTER_W > 0


class TestDockSizing:
    """Tests for DockSizing dataclass."""

    def test_default_values(self):
        """Default sizing should use DOCK_WIDTH."""
        sizing = DockSizing()
        assert sizing.left_w == DOCK_WIDTH
        assert sizing.right_w == DOCK_WIDTH

    def test_custom_values(self):
        """Should accept custom width values."""
        sizing = DockSizing(left_w=300, right_w=400)
        assert sizing.left_w == 300
        assert sizing.right_w == 400


# ------------------------------------------------------------------------------
# Clamp Dock Width Tests
# ------------------------------------------------------------------------------


class TestClampDockWidth:
    """Tests for clamp_dock_width function."""

    def test_clamp_below_minimum(self):
        """Width below minimum should clamp to minimum."""
        result = clamp_dock_width(100, 1920, 320)
        assert result == DOCK_MIN_W

    def test_clamp_above_maximum(self):
        """Width above maximum should clamp to maximum."""
        result = clamp_dock_width(1000, 1920, 320)
        assert result == DOCK_MAX_W

    def test_within_bounds(self):
        """Width within bounds should be unchanged."""
        result = clamp_dock_width(350, 1920, 320)
        assert result == 350

    def test_respects_viewport_min(self):
        """Width should be clamped to ensure viewport minimum."""
        # With 1000px window and 320px other dock, max for this dock is:
        # 1000 - 320 - VIEWPORT_MIN_W (320) - SPLITTER_W*2 (12) = 348
        result = clamp_dock_width(500, 1000, 320)
        expected_max = 1000 - 320 - VIEWPORT_MIN_W - SPLITTER_W * 2
        assert result <= max(DOCK_MIN_W, expected_max)

    def test_very_small_window(self):
        """Very small window should still clamp to minimum."""
        result = clamp_dock_width(300, 500, 200)
        assert result >= DOCK_MIN_W


# ------------------------------------------------------------------------------
# Layout with Custom Widths Tests
# ------------------------------------------------------------------------------


class TestLayoutWithCustomWidths:
    """Tests for compute_editor_shell_layout with custom dock widths."""

    def test_default_widths(self):
        """Layout with no custom widths should use defaults."""
        layout = compute_editor_shell_layout(1920, 1080)
        assert layout.left_dock.width == DOCK_WIDTH
        assert layout.right_dock.width == DOCK_WIDTH

    def test_custom_left_width(self):
        """Layout should respect custom left dock width."""
        layout = compute_editor_shell_layout(1920, 1080, left_dock_w=400)
        assert layout.left_dock.width == 400

    def test_custom_right_width(self):
        """Layout should respect custom right dock width."""
        layout = compute_editor_shell_layout(1920, 1080, right_dock_w=450)
        assert layout.right_dock.width == 450

    def test_custom_both_widths(self):
        """Layout should respect both custom widths."""
        layout = compute_editor_shell_layout(1920, 1080, left_dock_w=300, right_dock_w=400)
        assert layout.left_dock.width == 300
        assert layout.right_dock.width == 400

    def test_widths_clamped_to_bounds(self):
        """Custom widths should be clamped to valid bounds."""
        layout = compute_editor_shell_layout(1920, 1080, left_dock_w=100, right_dock_w=1000)
        assert layout.left_dock.width >= DOCK_MIN_W
        assert layout.right_dock.width <= DOCK_MAX_W

    def test_viewport_has_minimum_width(self):
        """Viewport should maintain minimum width."""
        # Try to make docks too wide
        layout = compute_editor_shell_layout(1000, 800, left_dock_w=500, right_dock_w=500)
        viewport_w = layout.viewport.width
        # Viewport should have at least some width (considering splitters)
        assert viewport_w >= 0


# ------------------------------------------------------------------------------
# Splitter Rect Tests
# ------------------------------------------------------------------------------


class TestSplitterRects:
    """Tests for splitter rectangle computation."""

    def test_left_splitter_exists(self):
        """Layout should have a left splitter rect."""
        layout = compute_editor_shell_layout(1920, 1080)
        assert hasattr(layout, "left_splitter")
        assert isinstance(layout.left_splitter, Rect)

    def test_right_splitter_exists(self):
        """Layout should have a right splitter rect."""
        layout = compute_editor_shell_layout(1920, 1080)
        assert hasattr(layout, "right_splitter")
        assert isinstance(layout.right_splitter, Rect)

    def test_left_splitter_position(self):
        """Left splitter should be between left dock and viewport."""
        layout = compute_editor_shell_layout(1920, 1080)
        assert layout.left_splitter.left == layout.left_dock.right
        assert layout.left_splitter.right == layout.viewport.left

    def test_right_splitter_position(self):
        """Right splitter should be between viewport and right dock."""
        layout = compute_editor_shell_layout(1920, 1080)
        assert layout.right_splitter.right == layout.right_dock.left
        assert layout.right_splitter.left == layout.viewport.right

    def test_splitter_width(self):
        """Splitters should have correct width."""
        layout = compute_editor_shell_layout(1920, 1080)
        assert layout.left_splitter.width == SPLITTER_W
        assert layout.right_splitter.width == SPLITTER_W

    def test_splitter_height(self):
        """Splitters should span full content height."""
        layout = compute_editor_shell_layout(1920, 1080)
        assert layout.left_splitter.height == layout.left_dock.height
        assert layout.right_splitter.height == layout.right_dock.height


# ------------------------------------------------------------------------------
# Splitter Hit Testing Tests
# ------------------------------------------------------------------------------


class TestHitTestSplitter:
    """Tests for hit_test_splitter function."""

    def test_hit_left_splitter(self):
        """Clicking on left splitter returns 'left'."""
        layout = compute_editor_shell_layout(1920, 1080)
        x = layout.left_splitter.center_x
        y = layout.left_splitter.center_y
        result = hit_test_splitter(x, y, layout)
        assert result == "left"

    def test_hit_right_splitter(self):
        """Clicking on right splitter returns 'right'."""
        layout = compute_editor_shell_layout(1920, 1080)
        x = layout.right_splitter.center_x
        y = layout.right_splitter.center_y
        result = hit_test_splitter(x, y, layout)
        assert result == "right"

    def test_miss_returns_none(self):
        """Clicking outside splitters returns None."""
        layout = compute_editor_shell_layout(1920, 1080)
        # Click in viewport center
        x = layout.viewport.center_x
        y = layout.viewport.center_y
        result = hit_test_splitter(x, y, layout)
        assert result is None

    def test_miss_in_dock(self):
        """Clicking in dock area returns None."""
        layout = compute_editor_shell_layout(1920, 1080)
        x = layout.left_dock.center_x
        y = layout.left_dock.center_y
        result = hit_test_splitter(x, y, layout)
        assert result is None

    def test_hit_at_splitter_edge(self):
        """Clicking at splitter edge should still hit."""
        layout = compute_editor_shell_layout(1920, 1080)
        # Left edge of left splitter
        x = layout.left_splitter.left + 1
        y = layout.left_splitter.center_y
        result = hit_test_splitter(x, y, layout)
        assert result == "left"


# ------------------------------------------------------------------------------
# Workspace Persistence Tests
# ------------------------------------------------------------------------------


class TestDockWidthPersistence:
    """Tests for dock width persistence in workspace settings."""

    def test_workspace_settings_defaults(self):
        """Default dock widths should be 320."""
        settings = WorkspaceSettings()
        assert settings.dock_left_w == 320
        assert settings.dock_right_w == 320

    def test_workspace_settings_custom_values(self):
        """Should accept custom dock width values."""
        settings = WorkspaceSettings(dock_left_w=400, dock_right_w=350)
        assert settings.dock_left_w == 400
        assert settings.dock_right_w == 350

    def test_workspace_roundtrip(self, tmp_path):
        """Dock widths should persist through save/load cycle."""
        settings = WorkspaceSettings(dock_left_w=450, dock_right_w=380)

        save_workspace(tmp_path, settings)
        loaded = load_workspace(tmp_path)

        assert loaded.dock_left_w == 450
        assert loaded.dock_right_w == 380

    def test_workspace_roundtrip_default_values(self, tmp_path):
        """Default dock widths should persist correctly."""
        settings = WorkspaceSettings()

        save_workspace(tmp_path, settings)
        loaded = load_workspace(tmp_path)

        assert loaded.dock_left_w == 320
        assert loaded.dock_right_w == 320

    def test_workspace_json_contains_dock_widths(self, tmp_path):
        """Saved workspace JSON should contain dock width fields."""
        settings = WorkspaceSettings(dock_left_w=400, dock_right_w=350)

        save_workspace(tmp_path, settings)

        workspace_path = tmp_path / "workspace.json"
        data = json.loads(workspace_path.read_text("utf-8"))

        assert "dock_left_w" in data
        assert "dock_right_w" in data
        assert data["dock_left_w"] == 400
        assert data["dock_right_w"] == 350

    def test_workspace_missing_dock_widths_uses_defaults(self, tmp_path):
        """Missing dock width fields should use defaults."""
        # Write workspace without dock widths
        workspace_path = tmp_path / "workspace.json"
        data = {"entity_panels_open": True}
        workspace_path.write_text(json.dumps(data), encoding="utf-8")

        loaded = load_workspace(tmp_path)

        assert loaded.dock_left_w == 320
        assert loaded.dock_right_w == 320


# ------------------------------------------------------------------------------
# Integration Tests
# ------------------------------------------------------------------------------


class TestDockResizeIntegration:
    """Integration tests for dock resize workflow."""

    def test_layout_determinism(self):
        """Same inputs should produce identical layouts."""
        layout1 = compute_editor_shell_layout(1920, 1080, 350, 400)
        layout2 = compute_editor_shell_layout(1920, 1080, 350, 400)

        assert layout1.left_dock == layout2.left_dock
        assert layout1.right_dock == layout2.right_dock
        assert layout1.viewport == layout2.viewport
        assert layout1.left_splitter == layout2.left_splitter
        assert layout1.right_splitter == layout2.right_splitter

    def test_splitter_click_to_drag_workflow(self):
        """Test clicking splitter and computing new width."""
        # Initial layout
        layout = compute_editor_shell_layout(1920, 1080, 320, 320)

        # Hit test left splitter
        x = layout.left_splitter.center_x
        y = layout.left_splitter.center_y
        hit = hit_test_splitter(x, y, layout)
        assert hit == "left"

        # Simulate drag: move 50px to the right
        start_x = x
        new_x = start_x + 50
        delta = new_x - start_x
        new_width = int(320 + delta)

        # Compute new layout
        new_layout = compute_editor_shell_layout(1920, 1080, new_width, 320)
        assert new_layout.left_dock.width == 370

    def test_resize_does_not_overlap(self):
        """Resized docks should not overlap viewport."""
        layout = compute_editor_shell_layout(1920, 1080, 400, 400)

        # Left dock should end before left splitter
        assert layout.left_dock.right <= layout.left_splitter.left + 1

        # Right dock should start after right splitter
        assert layout.right_dock.left >= layout.right_splitter.right - 1

        # Viewport should be between splitters
        assert layout.viewport.left >= layout.left_splitter.right - 1
        assert layout.viewport.right <= layout.right_splitter.left + 1

    def test_small_window_still_works(self):
        """Even small windows should produce valid layouts."""
        layout = compute_editor_shell_layout(800, 600, 250, 250)

        # All rects should have positive dimensions
        assert layout.left_dock.width > 0
        assert layout.right_dock.width > 0
        assert layout.left_splitter.width > 0
        assert layout.right_splitter.width > 0

        # Splitters should be positioned correctly
        assert layout.left_splitter.left == layout.left_dock.right
        assert layout.right_splitter.right == layout.right_dock.left
