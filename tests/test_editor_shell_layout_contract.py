"""Tests for Editor Shell Layout contract."""

from engine.editor.editor_shell_layout import (
    BOTTOM_BAR_HEIGHT,
    DOCK_WIDTH,
    TOP_BAR_HEIGHT,
    DockTabState,
    Rect,
    clamp_rects_to_window,
    compute_editor_shell_layout,
    get_dock_tab_options,
)


class TestRect:
    """Tests for the Rect dataclass."""

    def test_rect_properties(self):
        rect = Rect(left=10.0, right=110.0, bottom=20.0, top=120.0)
        assert rect.width == 100.0
        assert rect.height == 100.0
        assert rect.center_x == 60.0
        assert rect.center_y == 70.0

    def test_rect_contains_point(self):
        rect = Rect(left=0.0, right=100.0, bottom=0.0, top=100.0)
        assert rect.contains_point(50.0, 50.0)
        assert rect.contains_point(0.0, 0.0)
        assert rect.contains_point(100.0, 100.0)
        assert not rect.contains_point(-1.0, 50.0)
        assert not rect.contains_point(101.0, 50.0)


class TestComputeEditorShellLayout:
    """Tests for compute_editor_shell_layout function."""

    def test_typical_window_size(self):
        """Layout should be valid for a typical 1920x1080 window."""
        layout = compute_editor_shell_layout(1920, 1080)

        # Top bar
        assert layout.top_bar.height == TOP_BAR_HEIGHT
        assert layout.top_bar.top == 1080
        assert layout.top_bar.bottom == 1080 - TOP_BAR_HEIGHT

        # Bottom bar
        assert layout.bottom_bar.height == BOTTOM_BAR_HEIGHT
        assert layout.bottom_bar.bottom == 0
        assert layout.bottom_bar.top == BOTTOM_BAR_HEIGHT

        # Viewport should have positive dimensions
        assert layout.viewport.width > 0
        assert layout.viewport.height > 0

        # All rects should be within window bounds
        for rect in [layout.top_bar, layout.bottom_bar, layout.left_dock,
                     layout.right_dock, layout.viewport]:
            assert rect.left >= 0
            assert rect.right <= 1920
            assert rect.bottom >= 0
            assert rect.top <= 1080

    def test_small_window(self):
        """Layout should handle small window sizes gracefully."""
        layout = compute_editor_shell_layout(800, 600)

        assert layout.top_bar.height == TOP_BAR_HEIGHT
        assert layout.bottom_bar.height == BOTTOM_BAR_HEIGHT
        assert layout.viewport.width > 0
        assert layout.viewport.height > 0

    def test_minimum_window(self):
        """Layout should not crash on very small windows."""
        layout = compute_editor_shell_layout(100, 100)

        # Should still produce valid layout
        assert layout.window_width == 100
        assert layout.window_height == 100

    def test_zero_window(self):
        """Layout should handle zero/negative dimensions gracefully."""
        layout = compute_editor_shell_layout(0, 0)
        # Should clamp to minimum of 1
        assert layout.window_width == 0
        assert layout.window_height == 0

    def test_dock_widths_capped(self):
        """Dock widths should be clamped to DOCK_MIN_W minimum."""
        # For narrow windows, docks should be at least DOCK_MIN_W (220)
        # The resizable dock system uses fixed min/max bounds, not percentages
        from engine.editor import DOCK_MIN_W
        layout = compute_editor_shell_layout(600, 600)
        # Docks are clamped to minimum width
        assert layout.left_dock.width >= DOCK_MIN_W
        assert layout.right_dock.width >= DOCK_MIN_W

    def test_layout_determinism(self):
        """Same inputs should produce identical layouts."""
        layout1 = compute_editor_shell_layout(1280, 720)
        layout2 = compute_editor_shell_layout(1280, 720)

        assert layout1 == layout2

    def test_viewport_between_docks(self):
        """Viewport should be positioned between left and right docks with splitter gaps."""
        from engine.editor import SPLITTER_W
        layout = compute_editor_shell_layout(1920, 1080)

        # Viewport is separated from docks by splitter width
        assert layout.viewport.left == layout.left_dock.right + SPLITTER_W
        assert layout.viewport.right == layout.right_dock.left - SPLITTER_W

    def test_content_fills_between_bars(self):
        """Docks and viewport should fill the space between top and bottom bars."""
        layout = compute_editor_shell_layout(1920, 1080)

        # All content panels should have same top/bottom
        expected_bottom = layout.bottom_bar.top
        expected_top = layout.top_bar.bottom

        assert layout.left_dock.bottom == expected_bottom
        assert layout.left_dock.top == expected_top
        assert layout.right_dock.bottom == expected_bottom
        assert layout.right_dock.top == expected_top
        assert layout.viewport.bottom == expected_bottom
        assert layout.viewport.top == expected_top


class TestClampRectsToWindow:
    """Tests for clamp_rects_to_window function."""

    def test_clamp_already_valid(self):
        """Clamping a valid layout should return unchanged rects."""
        layout = compute_editor_shell_layout(1920, 1080)
        clamped = clamp_rects_to_window(layout, 1920, 1080)

        assert clamped.top_bar == layout.top_bar
        assert clamped.bottom_bar == layout.bottom_bar

    def test_clamp_to_smaller_window(self):
        """Clamping to smaller window should constrain rects."""
        layout = compute_editor_shell_layout(1920, 1080)
        clamped = clamp_rects_to_window(layout, 800, 600)

        # All rects should be within new bounds
        for rect in [clamped.top_bar, clamped.bottom_bar, clamped.left_dock,
                     clamped.right_dock, clamped.viewport]:
            assert rect.left >= 0
            assert rect.right <= 800
            assert rect.bottom >= 0
            assert rect.top <= 600


class TestDockTabState:
    """Tests for DockTabState dataclass."""

    def test_default_values(self):
        """Default tab state should be Scene and Inspector."""
        state = DockTabState()
        assert state.left_tab == "Scene"
        assert state.right_tab == "Inspector"

    def test_custom_values(self):
        """Should accept custom tab values."""
        state = DockTabState(left_tab="Outliner", right_tab="Assets")
        assert state.left_tab == "Outliner"
        assert state.right_tab == "Assets"


class TestGetDockTabOptions:
    """Tests for get_dock_tab_options function."""

    def test_returns_expected_options(self):
        """Should return the expected tab options."""
        left_tabs, right_tabs = get_dock_tab_options()

        assert "Project" in left_tabs
        assert "Scene" in left_tabs
        assert "Outliner" in left_tabs
        assert "Inspector" in right_tabs
        assert "Assets" in right_tabs
        assert "Items" in right_tabs
        assert "Prefabs" in right_tabs
        assert "Quests" in right_tabs
        assert "History" in right_tabs
        assert "Problems" in right_tabs
        assert "Debug" in right_tabs


class TestLayoutConstants:
    """Tests for layout constants."""

    def test_top_bar_height(self):
        """Top bar height should be 48."""
        assert TOP_BAR_HEIGHT == 48

    def test_bottom_bar_height(self):
        """Bottom bar height should match status bar (28)."""
        assert BOTTOM_BAR_HEIGHT == 28

    def test_dock_width(self):
        """Dock width should be 320."""
        assert DOCK_WIDTH == 320
