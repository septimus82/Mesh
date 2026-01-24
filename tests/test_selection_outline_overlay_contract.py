"""Contract tests for selection_outline_overlay module.

Tests overlay behavior with mocked arcade and controller.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch, call

import pytest

from engine.editor.selection_outline_overlay import (
    SelectionOutlineOverlay,
    OUTLINE_COLOR,
    PRIMARY_OUTLINE_COLOR,
    GROUP_BOUNDS_COLOR,
    OUTLINE_LINE_WIDTH,
    PRIMARY_LINE_WIDTH,
    GROUP_LINE_WIDTH,
)


# -----------------------------------------------------------------------------
# Fixtures
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_arcade() -> MagicMock:
    """Create mock arcade module."""
    arcade = MagicMock()
    arcade.draw_line = MagicMock()
    return arcade


@pytest.fixture
def mock_controller() -> MagicMock:
    """Create mock editor controller."""
    controller = MagicMock()
    controller.active = True
    controller._selected_entity_ids = []
    controller._primary_entity_id = None
    # Alt-drag duplicate state (default inactive)
    controller._alt_dup_active = False
    controller._alt_dup_original_selection = None
    controller._alt_dup_specs = None
    controller._alt_dup_pivot_new_id = None
    return controller


@pytest.fixture
def mock_scene_controller() -> MagicMock:
    """Create mock scene controller."""
    sc = MagicMock()
    sc.current_scene_data = {
        "entities": [
            {"id": "ent_1", "x": 100.0, "y": 100.0, "width": 32.0, "height": 32.0},
            {"id": "ent_2", "x": 200.0, "y": 100.0, "width": 32.0, "height": 32.0},
            {"id": "ent_3", "x": 150.0, "y": 200.0, "width": 32.0, "height": 32.0},
        ]
    }
    return sc


@pytest.fixture
def mock_window(mock_controller: MagicMock, mock_scene_controller: MagicMock) -> MagicMock:
    """Create mock window with controller and scene_controller."""
    window = MagicMock()
    window.editor_controller = mock_controller
    window.scene_controller = mock_scene_controller
    return window


# -----------------------------------------------------------------------------
# SelectionOutlineOverlay initialization
# -----------------------------------------------------------------------------


class TestOverlayInit:
    """Tests for overlay initialization."""

    def test_creates_with_window(self, mock_window: MagicMock) -> None:
        overlay = SelectionOutlineOverlay(mock_window)
        assert overlay.window is mock_window
        assert overlay._visible is True

    def test_controller_property(self, mock_window: MagicMock) -> None:
        overlay = SelectionOutlineOverlay(mock_window)
        assert overlay.controller is mock_window.editor_controller


# -----------------------------------------------------------------------------
# draw_world with no selection
# -----------------------------------------------------------------------------


class TestDrawWorldNoSelection:
    """Tests for draw_world when nothing is selected."""

    def test_no_draw_when_editor_inactive(
        self, mock_window: MagicMock, mock_arcade: MagicMock
    ) -> None:
        mock_window.editor_controller.active = False
        overlay = SelectionOutlineOverlay(mock_window)

        with patch("engine.editor.selection_outline_overlay.optional_arcade") as mock_oa:
            mock_oa.arcade = mock_arcade
            overlay.draw_world()

        mock_arcade.draw_line.assert_not_called()

    def test_no_draw_when_no_selection(
        self, mock_window: MagicMock, mock_arcade: MagicMock
    ) -> None:
        mock_window.editor_controller._selected_entity_ids = []
        overlay = SelectionOutlineOverlay(mock_window)

        with patch("engine.editor.selection_outline_overlay.optional_arcade") as mock_oa:
            mock_oa.arcade = mock_arcade
            overlay.draw_world()

        mock_arcade.draw_line.assert_not_called()


# -----------------------------------------------------------------------------
# draw_world with single selection
# -----------------------------------------------------------------------------


class TestDrawWorldSingleSelection:
    """Tests for draw_world with single entity selected."""

    def test_draws_outline_for_single_selection(
        self, mock_window: MagicMock, mock_arcade: MagicMock
    ) -> None:
        mock_window.editor_controller._selected_entity_ids = ["ent_1"]
        mock_window.editor_controller._primary_entity_id = "ent_1"
        overlay = SelectionOutlineOverlay(mock_window)

        with patch("engine.editor.selection_outline_overlay.optional_arcade") as mock_oa:
            mock_oa.arcade = mock_arcade
            with patch.object(overlay, "_build_sprite_lookup", return_value={}):
                overlay.draw_world()

        # Should have drawn lines (4 for border + 8 for corner markers)
        assert mock_arcade.draw_line.call_count >= 4

    def test_uses_primary_color_for_single(
        self, mock_window: MagicMock, mock_arcade: MagicMock
    ) -> None:
        mock_window.editor_controller._selected_entity_ids = ["ent_1"]
        mock_window.editor_controller._primary_entity_id = "ent_1"
        overlay = SelectionOutlineOverlay(mock_window)

        with patch("engine.editor.selection_outline_overlay.optional_arcade") as mock_oa:
            mock_oa.arcade = mock_arcade
            with patch.object(overlay, "_build_sprite_lookup", return_value={}):
                overlay.draw_world()

        # Check that primary color was used in at least one call
        calls = mock_arcade.draw_line.call_args_list
        colors_used = [c[0][4] for c in calls if len(c[0]) > 4]
        assert PRIMARY_OUTLINE_COLOR in colors_used


# -----------------------------------------------------------------------------
# draw_world with multi-selection
# -----------------------------------------------------------------------------


class TestDrawWorldMultiSelection:
    """Tests for draw_world with multiple entities selected."""

    def test_draws_group_bounds_for_multi_select(
        self, mock_window: MagicMock, mock_arcade: MagicMock
    ) -> None:
        mock_window.editor_controller._selected_entity_ids = ["ent_1", "ent_2"]
        mock_window.editor_controller._primary_entity_id = "ent_1"
        overlay = SelectionOutlineOverlay(mock_window)

        with patch("engine.editor.selection_outline_overlay.optional_arcade") as mock_oa:
            mock_oa.arcade = mock_arcade
            with patch.object(overlay, "_build_sprite_lookup", return_value={}):
                overlay.draw_world()

        # Should draw: group bounds (4) + ent_2 outline (4) + ent_1 outline (4) + corners (8)
        # At minimum 12 lines for 2 entities + group
        assert mock_arcade.draw_line.call_count >= 12

    def test_uses_group_bounds_color(
        self, mock_window: MagicMock, mock_arcade: MagicMock
    ) -> None:
        mock_window.editor_controller._selected_entity_ids = ["ent_1", "ent_2"]
        mock_window.editor_controller._primary_entity_id = "ent_1"
        overlay = SelectionOutlineOverlay(mock_window)

        with patch("engine.editor.selection_outline_overlay.optional_arcade") as mock_oa:
            mock_oa.arcade = mock_arcade
            with patch.object(overlay, "_build_sprite_lookup", return_value={}):
                overlay.draw_world()

        # Check that group bounds color was used
        calls = mock_arcade.draw_line.call_args_list
        colors_used = [c[0][4] for c in calls if len(c[0]) > 4]
        assert GROUP_BOUNDS_COLOR in colors_used

    def test_draws_non_primary_with_outline_color(
        self, mock_window: MagicMock, mock_arcade: MagicMock
    ) -> None:
        mock_window.editor_controller._selected_entity_ids = ["ent_1", "ent_2"]
        mock_window.editor_controller._primary_entity_id = "ent_1"
        overlay = SelectionOutlineOverlay(mock_window)

        with patch("engine.editor.selection_outline_overlay.optional_arcade") as mock_oa:
            mock_oa.arcade = mock_arcade
            with patch.object(overlay, "_build_sprite_lookup", return_value={}):
                overlay.draw_world()

        # Check that regular outline color was used
        calls = mock_arcade.draw_line.call_args_list
        colors_used = [c[0][4] for c in calls if len(c[0]) > 4]
        assert OUTLINE_COLOR in colors_used


# -----------------------------------------------------------------------------
# Entity lookup helpers
# -----------------------------------------------------------------------------


class TestEntityLookupHelpers:
    """Tests for entity lookup helper methods."""

    def test_get_selected_entity_ids(self, mock_window: MagicMock) -> None:
        mock_window.editor_controller._selected_entity_ids = ["a", "b", "c"]
        overlay = SelectionOutlineOverlay(mock_window)

        result = overlay._get_selected_entity_ids(mock_window.editor_controller)
        assert result == ["a", "b", "c"]
        # Should be a copy
        result.append("d")
        assert mock_window.editor_controller._selected_entity_ids == ["a", "b", "c"]

    def test_get_primary_entity_id(self, mock_window: MagicMock) -> None:
        mock_window.editor_controller._primary_entity_id = "primary_ent"
        overlay = SelectionOutlineOverlay(mock_window)

        result = overlay._get_primary_entity_id(mock_window.editor_controller)
        assert result == "primary_ent"

    def test_get_primary_entity_id_none(self, mock_window: MagicMock) -> None:
        mock_window.editor_controller._primary_entity_id = None
        overlay = SelectionOutlineOverlay(mock_window)

        result = overlay._get_primary_entity_id(mock_window.editor_controller)
        assert result is None

    def test_build_entity_lookup(self, mock_window: MagicMock) -> None:
        overlay = SelectionOutlineOverlay(mock_window)

        result = overlay._build_entity_lookup(mock_window.editor_controller)

        assert "ent_1" in result
        assert "ent_2" in result
        assert "ent_3" in result
        assert result["ent_1"]["x"] == 100.0


# -----------------------------------------------------------------------------
# Visibility toggle
# -----------------------------------------------------------------------------


class TestVisibility:
    """Tests for visibility toggle."""

    def test_no_draw_when_not_visible(
        self, mock_window: MagicMock, mock_arcade: MagicMock
    ) -> None:
        mock_window.editor_controller._selected_entity_ids = ["ent_1"]
        overlay = SelectionOutlineOverlay(mock_window)
        overlay._visible = False

        with patch("engine.editor.selection_outline_overlay.optional_arcade") as mock_oa:
            mock_oa.arcade = mock_arcade
            overlay.draw_world()

        mock_arcade.draw_line.assert_not_called()


# -----------------------------------------------------------------------------
# draw_ui
# -----------------------------------------------------------------------------


class TestDrawUI:
    """Tests for draw_ui method."""

    def test_draw_ui_does_not_crash(self, mock_window: MagicMock) -> None:
        overlay = SelectionOutlineOverlay(mock_window)
        # Should not raise
        overlay.draw_ui()
