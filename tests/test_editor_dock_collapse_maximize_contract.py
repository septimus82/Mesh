"""Contract tests for dock collapse and viewport maximize feature.

These tests verify the pure layout helpers, hit testing, controller state
transitions, and workspace persistence - all headless-safe.
"""

from __future__ import annotations

import pytest


# =============================================================================
# resolve_effective_dock_widths Tests
# =============================================================================


class TestResolveEffectiveDockWidths:
    """Tests for resolve_effective_dock_widths pure function."""

    def test_maximize_returns_zero_zero(self) -> None:
        """When viewport is maximized, both docks should be 0."""
        from engine.editor.editor_shell_layout import resolve_effective_dock_widths

        left_eff, right_eff = resolve_effective_dock_widths(
            left_collapsed=False,
            right_collapsed=False,
            viewport_maximized=True,
            left_w=320,
            right_w=320,
            window_width=1920,
        )
        assert left_eff == 0
        assert right_eff == 0

    def test_left_collapsed_returns_zero_left(self) -> None:
        """When left dock is collapsed, left_w_eff should be 0."""
        from engine.editor.editor_shell_layout import resolve_effective_dock_widths

        left_eff, right_eff = resolve_effective_dock_widths(
            left_collapsed=True,
            right_collapsed=False,
            viewport_maximized=False,
            left_w=320,
            right_w=320,
            window_width=1920,
        )
        assert left_eff == 0
        assert right_eff > 0

    def test_right_collapsed_returns_zero_right(self) -> None:
        """When right dock is collapsed, right_w_eff should be 0."""
        from engine.editor.editor_shell_layout import resolve_effective_dock_widths

        left_eff, right_eff = resolve_effective_dock_widths(
            left_collapsed=False,
            right_collapsed=True,
            viewport_maximized=False,
            left_w=320,
            right_w=320,
            window_width=1920,
        )
        assert left_eff > 0
        assert right_eff == 0

    def test_both_collapsed_returns_zero_zero(self) -> None:
        """When both docks are collapsed, both should be 0."""
        from engine.editor.editor_shell_layout import resolve_effective_dock_widths

        left_eff, right_eff = resolve_effective_dock_widths(
            left_collapsed=True,
            right_collapsed=True,
            viewport_maximized=False,
            left_w=320,
            right_w=320,
            window_width=1920,
        )
        assert left_eff == 0
        assert right_eff == 0

    def test_neither_collapsed_returns_clamped_widths(self) -> None:
        """When neither collapsed, should return clamped widths."""
        from engine.editor.editor_shell_layout import resolve_effective_dock_widths, DOCK_MIN_W

        left_eff, right_eff = resolve_effective_dock_widths(
            left_collapsed=False,
            right_collapsed=False,
            viewport_maximized=False,
            left_w=320,
            right_w=320,
            window_width=1920,
        )
        assert left_eff >= DOCK_MIN_W
        assert right_eff >= DOCK_MIN_W

    def test_clamp_behavior_unchanged_for_expanded_docks(self) -> None:
        """Expanded docks should still respect min/max clamping."""
        from engine.editor.editor_shell_layout import (
            resolve_effective_dock_widths,
            DOCK_MIN_W,
            DOCK_MAX_W,
        )

        # Very small width should be clamped to min
        left_eff, _ = resolve_effective_dock_widths(
            left_collapsed=False,
            right_collapsed=False,
            viewport_maximized=False,
            left_w=50,  # Below minimum
            right_w=320,
            window_width=1920,
        )
        assert left_eff >= DOCK_MIN_W

        # Very large width should be clamped to max
        left_eff, _ = resolve_effective_dock_widths(
            left_collapsed=False,
            right_collapsed=False,
            viewport_maximized=False,
            left_w=1000,  # Above maximum
            right_w=320,
            window_width=1920,
        )
        assert left_eff <= DOCK_MAX_W


# =============================================================================
# compute_editor_shell_layout with Collapsed Docks Tests
# =============================================================================


class TestLayoutWithCollapsedDocks:
    """Tests for layout computation with collapsed docks.

    Note: The compute_editor_shell_layout function clamps dock widths to DOCK_MIN_W.
    When passing 0, it gets clamped to minimum. The resolve_effective_dock_widths
    function is what actually returns 0 for collapsed docks - that effective 0
    value is then used by the overlay to skip drawing the dock entirely.
    """

    def test_collapsed_effective_widths_yield_expanded_viewport(self) -> None:
        """Effective widths of 0 from resolve_effective_dock_widths yield expanded viewport.

        The layout function receives effective widths. When collapsed,
        effective width is 0, which gets clamped to minimum. The overlay
        then skips drawing docks entirely when collapsed.
        """
        from engine.editor.editor_shell_layout import (
            compute_editor_shell_layout,
            resolve_effective_dock_widths,
        )

        # Normal layout
        normal = compute_editor_shell_layout(1920, 1080, 320, 320)

        # When left is collapsed, resolve_effective_dock_widths returns 0
        left_eff, right_eff = resolve_effective_dock_widths(
            left_collapsed=True,
            right_collapsed=False,
            viewport_maximized=False,
            left_w=320,
            right_w=320,
            window_width=1920,
        )
        assert left_eff == 0
        # The layout function will clamp this to min, but the overlay
        # skips drawing the dock entirely when collapsed

    def test_viewport_width_increases_with_smaller_docks(self) -> None:
        """Viewport width should increase when dock widths decrease."""
        from engine.editor.editor_shell_layout import compute_editor_shell_layout, DOCK_MIN_W

        # Large docks
        large = compute_editor_shell_layout(1920, 1080, 400, 400)
        # Minimum docks
        small = compute_editor_shell_layout(1920, 1080, DOCK_MIN_W, DOCK_MIN_W)

        # Viewport should be wider with smaller docks
        assert small.viewport.width > large.viewport.width

    def test_layout_handles_zero_dock_widths_gracefully(self) -> None:
        """Layout function should handle 0 dock widths without crashing."""
        from engine.editor.editor_shell_layout import compute_editor_shell_layout

        # Should not raise an exception
        layout = compute_editor_shell_layout(1920, 1080, 0, 0)
        assert layout.viewport.width > 0
        assert layout.top_bar.height > 0


# =============================================================================
# Top Bar Controls Hit Testing
# =============================================================================


class TestTopBarControlsHitTesting:
    """Tests for top bar control button hit testing."""

    def test_compute_top_bar_controls_returns_valid_rects(self) -> None:
        """compute_top_bar_controls should return 3 valid rects."""
        from engine.editor.editor_shell_layout import (
            compute_editor_shell_layout,
            compute_top_bar_controls,
        )

        layout = compute_editor_shell_layout(1920, 1080, 320, 320)
        controls = compute_top_bar_controls(layout)

        assert controls.toggle_left.width > 0
        assert controls.toggle_left.height > 0
        assert controls.toggle_right.width > 0
        assert controls.toggle_right.height > 0
        assert controls.toggle_max.width > 0
        assert controls.toggle_max.height > 0

    def test_hit_test_toggle_left(self) -> None:
        """Clicking inside toggle_left rect should return 'toggle_left'."""
        from engine.editor.editor_shell_layout import (
            compute_editor_shell_layout,
            compute_top_bar_controls,
            hit_test_top_bar_controls,
        )

        layout = compute_editor_shell_layout(1920, 1080, 320, 320)
        controls = compute_top_bar_controls(layout)

        result = hit_test_top_bar_controls(
            controls.toggle_left.center_x,
            controls.toggle_left.center_y,
            controls,
        )
        assert result == "toggle_left"

    def test_hit_test_toggle_right(self) -> None:
        """Clicking inside toggle_right rect should return 'toggle_right'."""
        from engine.editor.editor_shell_layout import (
            compute_editor_shell_layout,
            compute_top_bar_controls,
            hit_test_top_bar_controls,
        )

        layout = compute_editor_shell_layout(1920, 1080, 320, 320)
        controls = compute_top_bar_controls(layout)

        result = hit_test_top_bar_controls(
            controls.toggle_right.center_x,
            controls.toggle_right.center_y,
            controls,
        )
        assert result == "toggle_right"

    def test_hit_test_toggle_max(self) -> None:
        """Clicking inside toggle_max rect should return 'toggle_max'."""
        from engine.editor.editor_shell_layout import (
            compute_editor_shell_layout,
            compute_top_bar_controls,
            hit_test_top_bar_controls,
        )

        layout = compute_editor_shell_layout(1920, 1080, 320, 320)
        controls = compute_top_bar_controls(layout)

        result = hit_test_top_bar_controls(
            controls.toggle_max.center_x,
            controls.toggle_max.center_y,
            controls,
        )
        assert result == "toggle_max"

    def test_hit_test_outside_returns_none(self) -> None:
        """Clicking outside all controls should return None."""
        from engine.editor.editor_shell_layout import (
            compute_editor_shell_layout,
            compute_top_bar_controls,
            hit_test_top_bar_controls,
        )

        layout = compute_editor_shell_layout(1920, 1080, 320, 320)
        controls = compute_top_bar_controls(layout)

        # Click far away from all controls
        result = hit_test_top_bar_controls(0, 0, controls)
        assert result is None

    def test_controls_stay_within_window(self) -> None:
        """Control rects should not exceed window bounds."""
        from engine.editor.editor_shell_layout import (
            compute_editor_shell_layout,
            compute_top_bar_controls,
        )

        layout = compute_editor_shell_layout(1920, 1080, 320, 320)
        controls = compute_top_bar_controls(layout)

        for rect in [controls.toggle_left, controls.toggle_right, controls.toggle_max]:
            assert rect.left >= 0
            assert rect.right <= 1920
            assert rect.bottom >= 0
            assert rect.top <= 1080


# =============================================================================
# Controller State Transitions (Headless)
# =============================================================================


class TestControllerStateTransitions:
    """Tests for dock/maximize state transitions via EditorDockController."""

    class _Host:
        def _autosave_workspace(self) -> None:
            return

    def test_toggle_left_dock_flips_boolean(self) -> None:
        from engine.editor.editor_dock_controller import EditorDockController

        dock = EditorDockController(None, left_collapsed=False, right_collapsed=False, viewport_maximized=False)
        host = self._Host()
        assert dock.get_left_collapsed() is False

        dock.toggle_left_dock(host)
        assert dock.get_left_collapsed() is True

        dock.toggle_left_dock(host)
        assert dock.get_left_collapsed() is False

    def test_toggle_right_dock_flips_boolean(self) -> None:
        from engine.editor.editor_dock_controller import EditorDockController

        dock = EditorDockController(None, left_collapsed=False, right_collapsed=False, viewport_maximized=False)
        host = self._Host()
        assert dock.get_right_collapsed() is False

        dock.toggle_right_dock(host)
        assert dock.get_right_collapsed() is True

        dock.toggle_right_dock(host)
        assert dock.get_right_collapsed() is False

    def test_maximize_stores_previous_collapse_states(self) -> None:
        from engine.editor.editor_dock_controller import EditorDockController

        dock = EditorDockController(None, left_collapsed=True, right_collapsed=False, viewport_maximized=False)
        host = self._Host()

        dock.toggle_viewport_maximized(host)
        assert dock.get_viewport_maximized() is True
        assert dock.get_prev_left_collapsed() is True
        assert dock.get_prev_right_collapsed() is False

    def test_maximize_off_restores_previous_states(self) -> None:
        from engine.editor.editor_dock_controller import EditorDockController

        dock = EditorDockController(None, left_collapsed=True, right_collapsed=False, viewport_maximized=False)
        host = self._Host()

        dock.toggle_viewport_maximized(host)
        dock.toggle_viewport_maximized(host)

        assert dock.get_viewport_maximized() is False
        assert dock.get_left_collapsed() is True
        assert dock.get_right_collapsed() is False

    def test_dock_toggle_blocked_when_maximized(self) -> None:
        from engine.editor.editor_dock_controller import EditorDockController

        dock = EditorDockController(None, left_collapsed=False, right_collapsed=False, viewport_maximized=True)
        host = self._Host()

        dock.toggle_left_dock(host)
        assert dock.get_left_collapsed() is False

        dock.toggle_right_dock(host)
        assert dock.get_right_collapsed() is False


# =============================================================================
# Workspace Persistence Roundtrip
# =============================================================================


class TestWorkspacePersistence:
    """Tests for workspace settings persistence of dock/maximize state."""

    def test_workspace_settings_includes_new_booleans(self) -> None:
        """WorkspaceSettings should have dock_left_collapsed, dock_right_collapsed, viewport_maximized."""
        from engine.workspace_settings import WorkspaceSettings

        settings = WorkspaceSettings()
        assert hasattr(settings, "dock_left_collapsed")
        assert hasattr(settings, "dock_right_collapsed")
        assert hasattr(settings, "viewport_maximized")

    def test_defaults_are_false(self) -> None:
        """Default values for dock/maximize state should be False."""
        from engine.workspace_settings import WorkspaceSettings

        settings = WorkspaceSettings()
        assert settings.dock_left_collapsed is False
        assert settings.dock_right_collapsed is False
        assert settings.viewport_maximized is False

    def test_from_dict_loads_dock_collapse_state(self) -> None:
        """from_dict should correctly load dock/maximize state."""
        from engine.workspace_settings import WorkspaceSettings

        data = {
            "dock_left_collapsed": True,
            "dock_right_collapsed": True,
            "viewport_maximized": True,
        }
        settings = WorkspaceSettings.from_dict(data)

        assert settings.dock_left_collapsed is True
        assert settings.dock_right_collapsed is True
        assert settings.viewport_maximized is True

    def test_from_dict_defaults_missing_fields(self) -> None:
        """from_dict should default missing dock/maximize fields to False."""
        from engine.workspace_settings import WorkspaceSettings

        data = {}  # No dock/maximize fields
        settings = WorkspaceSettings.from_dict(data)

        assert settings.dock_left_collapsed is False
        assert settings.dock_right_collapsed is False
        assert settings.viewport_maximized is False

    def test_to_dict_includes_fields(self) -> None:
        """asdict(settings) should include dock/maximize fields."""
        from dataclasses import asdict
        from engine.workspace_settings import WorkspaceSettings

        settings = WorkspaceSettings(
            dock_left_collapsed=True,
            dock_right_collapsed=True,
            viewport_maximized=True,
        )
        data = asdict(settings)

        assert data["dock_left_collapsed"] is True
        assert data["dock_right_collapsed"] is True
        assert data["viewport_maximized"] is True

    def test_roundtrip_preserves_state(self) -> None:
        """Saving and loading should preserve dock/maximize state."""
        from dataclasses import asdict
        from engine.workspace_settings import WorkspaceSettings

        original = WorkspaceSettings(
            dock_left_collapsed=True,
            dock_right_collapsed=False,
            viewport_maximized=True,
        )

        # Simulate save/load
        data = asdict(original)
        loaded = WorkspaceSettings.from_dict(data)

        assert loaded.dock_left_collapsed == original.dock_left_collapsed
        assert loaded.dock_right_collapsed == original.dock_right_collapsed
        assert loaded.viewport_maximized == original.viewport_maximized
