"""Unit tests for editor_hover_highlight_model.py.

Verifies pure hover highlight computation functions are deterministic,
headless-safe, and correctly prioritize UI elements.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.editor_hover_highlight_model import (
    HoverHighlightKind,
    HoverHighlightSpec,
    HighlightRect,
    is_ui_blocked,
    resolve_hover_highlights,
)
from tests._typing import as_any
from tests._session_stub import make_session_stub


def _make_controller(**attrs: object) -> object:
    attrs.setdefault("session", make_session_stub())
    return type("MockController", (), attrs)()


class TestHighlightRect:
    """Tests for HighlightRect dataclass."""

    def test_basic_properties(self) -> None:
        """Test basic rect properties."""
        r = HighlightRect(x=10, y=20, w=100, h=50)
        assert r.left == 10
        assert r.right == 110
        assert r.bottom == 20
        assert r.top == 70
        assert r.w == 100
        assert r.h == 50

    def test_contains_point_inside(self) -> None:
        """Test point inside rect."""
        r = HighlightRect(x=0, y=0, w=100, h=100)
        assert r.contains_point(50, 50)
        assert r.contains_point(0, 0)
        assert r.contains_point(100, 100)
        assert r.contains_point(0, 100)

    def test_contains_point_outside(self) -> None:
        """Test point outside rect."""
        r = HighlightRect(x=10, y=10, w=50, h=50)
        assert not r.contains_point(0, 0)
        assert not r.contains_point(100, 100)
        assert not r.contains_point(5, 35)  # Left of rect
        assert not r.contains_point(35, 5)  # Below rect

    def test_clamped_within_bounds(self) -> None:
        """Test clamping rect within window bounds."""
        r = HighlightRect(x=10, y=20, w=50, h=30)
        clamped = r.clamped(1280, 720)
        assert clamped == r

    def test_clamped_overflow_right(self) -> None:
        """Test clamping rect that overflows right edge."""
        r = HighlightRect(x=1200, y=100, w=200, h=50)
        clamped = r.clamped(1280, 720)
        assert clamped.right == 1280
        assert clamped.left == 1200
        assert clamped.w == 80

    def test_clamped_overflow_top(self) -> None:
        """Test clamping rect that overflows top edge."""
        r = HighlightRect(x=100, y=700, w=50, h=100)
        clamped = r.clamped(1280, 720)
        assert clamped.top == 720
        assert clamped.h == 20

    def test_clamped_negative_origin(self) -> None:
        """Test clamping rect with negative origin."""
        r = HighlightRect(x=-50, y=-30, w=100, h=80)
        clamped = r.clamped(1280, 720)
        assert clamped.left == 0
        assert clamped.bottom == 0
        assert clamped.w == 50  # Only right portion inside
        assert clamped.h == 50  # Only top portion inside

    def test_frozen_immutable(self) -> None:
        """Test that HighlightRect is immutable."""
        r = HighlightRect(x=10, y=20, w=100, h=50)
        with pytest.raises(AttributeError):
            as_any(r).x = 99


class TestHoverHighlightSpec:
    """Tests for HoverHighlightSpec dataclass."""

    def test_basic_ui_spec(self) -> None:
        """Test basic UI-space highlight spec."""
        rect = HighlightRect(x=0, y=0, w=100, h=30)
        spec = HoverHighlightSpec(
            kind=HoverHighlightKind.MENU_TITLE,
            rect=rect,
            label="File",
        )
        assert spec.kind == HoverHighlightKind.MENU_TITLE
        assert spec.label == "File"
        assert spec.is_world_space is False

    def test_entity_spec_world_space(self) -> None:
        """Test world-space entity highlight spec."""
        rect = HighlightRect(x=100, y=200, w=32, h=32)
        spec = HoverHighlightSpec(
            kind=HoverHighlightKind.ENTITY_HOVER,
            rect=rect,
            label="entity_123",
            is_world_space=True,
        )
        assert spec.kind == HoverHighlightKind.ENTITY_HOVER
        assert spec.is_world_space is True

    def test_frozen_immutable(self) -> None:
        """Test that HoverHighlightSpec is immutable."""
        rect = HighlightRect(x=0, y=0, w=100, h=30)
        spec = HoverHighlightSpec(kind=HoverHighlightKind.DOCK_TAB, rect=rect)
        with pytest.raises(AttributeError):
            as_any(spec).kind = HoverHighlightKind.SPLITTER


class TestResolveHoverHighlights:
    """Tests for resolve_hover_highlights function."""

    def test_returns_empty_when_blocked(self) -> None:
        """Test returns empty tuple when block_ui=True."""
        result = resolve_hover_highlights(
            window_w=1280,
            window_h=720,
            hovered_menu_title="File",
            hovered_menu_title_rect=(10, 690, 50, 25),
            hovered_menu_item_id=None,
            hovered_menu_item_rect=None,
            hovered_top_bar_control_id=None,
            hovered_context_item_id=None,
            hovered_context_item_rect=None,
            hovered_dock_tab=None,
            hovered_dock_tab_rect=None,
            hovered_splitter=None,
            hovered_splitter_rect=None,
            hovered_inspector_field_key=None,
            hovered_inspector_field_rect=None,
            hovered_entity_id=None,
            hovered_entity_rect=None,
            block_ui=True,
        )
        assert result == ()

    def test_returns_empty_when_no_hover(self) -> None:
        """Test returns empty tuple when nothing hovered."""
        result = resolve_hover_highlights(
            window_w=1280,
            window_h=720,
            hovered_menu_title=None,
            hovered_menu_title_rect=None,
            hovered_menu_item_id=None,
            hovered_menu_item_rect=None,
            hovered_top_bar_control_id=None,
            hovered_context_item_id=None,
            hovered_context_item_rect=None,
            hovered_dock_tab=None,
            hovered_dock_tab_rect=None,
            hovered_splitter=None,
            hovered_splitter_rect=None,
            hovered_inspector_field_key=None,
            hovered_inspector_field_rect=None,
            hovered_entity_id=None,
            hovered_entity_rect=None,
            block_ui=False,
        )
        assert result == ()

    def test_menu_title_highlight(self) -> None:
        """Test menu title hover produces correct spec."""
        result = resolve_hover_highlights(
            window_w=1280,
            window_h=720,
            hovered_menu_title="File",
            hovered_menu_title_rect=(10, 695, 50, 25),
            hovered_menu_item_id=None,
            hovered_menu_item_rect=None,
            hovered_top_bar_control_id=None,
            hovered_context_item_id=None,
            hovered_context_item_rect=None,
            hovered_dock_tab=None,
            hovered_dock_tab_rect=None,
            hovered_splitter=None,
            hovered_splitter_rect=None,
            hovered_inspector_field_key=None,
            hovered_inspector_field_rect=None,
            hovered_entity_id=None,
            hovered_entity_rect=None,
            block_ui=False,
        )
        assert len(result) == 1
        assert result[0].kind == HoverHighlightKind.MENU_TITLE
        assert result[0].label == "File"
        assert result[0].rect.left == 10
        assert result[0].is_world_space is False

    def test_menu_item_highlight(self) -> None:
        """Test menu item hover produces correct spec."""
        result = resolve_hover_highlights(
            window_w=1280,
            window_h=720,
            hovered_menu_title=None,
            hovered_menu_title_rect=None,
            hovered_menu_item_id="file_save",
            hovered_menu_item_rect=(10, 650, 150, 25),
            hovered_top_bar_control_id=None,
            hovered_context_item_id=None,
            hovered_context_item_rect=None,
            hovered_dock_tab=None,
            hovered_dock_tab_rect=None,
            hovered_splitter=None,
            hovered_splitter_rect=None,
            hovered_inspector_field_key=None,
            hovered_inspector_field_rect=None,
            hovered_entity_id=None,
            hovered_entity_rect=None,
            block_ui=False,
        )
        assert len(result) == 1
        assert result[0].kind == HoverHighlightKind.MENU_ITEM
        assert result[0].label == "file_save"

    def test_top_bar_control_left_highlight(self) -> None:
        """Test top bar left control hover produces correct spec."""
        from engine.editor.editor_shell_layout import (
            compute_editor_shell_layout,
            compute_top_bar_controls,
        )

        layout = compute_editor_shell_layout(1280, 720)
        controls = compute_top_bar_controls(layout)

        result = resolve_hover_highlights(
            window_w=1280,
            window_h=720,
            hovered_menu_title=None,
            hovered_menu_title_rect=None,
            hovered_menu_item_id=None,
            hovered_menu_item_rect=None,
            hovered_top_bar_control_id="L",
            hovered_context_item_id=None,
            hovered_context_item_rect=None,
            hovered_dock_tab=None,
            hovered_dock_tab_rect=None,
            hovered_splitter=None,
            hovered_splitter_rect=None,
            hovered_inspector_field_key=None,
            hovered_inspector_field_rect=None,
            hovered_entity_id=None,
            hovered_entity_rect=None,
            block_ui=False,
        )

        assert len(result) == 1
        assert result[0].kind == HoverHighlightKind.TOPBAR_CONTROL
        assert result[0].label == "Toggle Left Dock"
        assert result[0].rect.left == controls.toggle_left.left
        assert result[0].rect.bottom == controls.toggle_left.bottom
        assert result[0].rect.w == controls.toggle_left.width
        assert result[0].rect.h == controls.toggle_left.height

    def test_top_bar_control_right_highlight(self) -> None:
        """Test top bar right control hover produces correct spec."""
        from engine.editor.editor_shell_layout import (
            compute_editor_shell_layout,
            compute_top_bar_controls,
        )

        layout = compute_editor_shell_layout(1280, 720)
        controls = compute_top_bar_controls(layout)

        result = resolve_hover_highlights(
            window_w=1280,
            window_h=720,
            hovered_menu_title=None,
            hovered_menu_title_rect=None,
            hovered_menu_item_id=None,
            hovered_menu_item_rect=None,
            hovered_top_bar_control_id="R",
            hovered_context_item_id=None,
            hovered_context_item_rect=None,
            hovered_dock_tab=None,
            hovered_dock_tab_rect=None,
            hovered_splitter=None,
            hovered_splitter_rect=None,
            hovered_inspector_field_key=None,
            hovered_inspector_field_rect=None,
            hovered_entity_id=None,
            hovered_entity_rect=None,
            block_ui=False,
        )

        assert len(result) == 1
        assert result[0].kind == HoverHighlightKind.TOPBAR_CONTROL
        assert result[0].label == "Toggle Right Dock"
        assert result[0].rect.left == controls.toggle_right.left
        assert result[0].rect.bottom == controls.toggle_right.bottom
        assert result[0].rect.w == controls.toggle_right.width
        assert result[0].rect.h == controls.toggle_right.height

    def test_top_bar_control_max_highlight(self) -> None:
        """Test top bar max control hover produces correct spec."""
        from engine.editor.editor_shell_layout import (
            compute_editor_shell_layout,
            compute_top_bar_controls,
        )

        layout = compute_editor_shell_layout(1280, 720)
        controls = compute_top_bar_controls(layout)

        result = resolve_hover_highlights(
            window_w=1280,
            window_h=720,
            hovered_menu_title=None,
            hovered_menu_title_rect=None,
            hovered_menu_item_id=None,
            hovered_menu_item_rect=None,
            hovered_top_bar_control_id="M",
            hovered_context_item_id=None,
            hovered_context_item_rect=None,
            hovered_dock_tab=None,
            hovered_dock_tab_rect=None,
            hovered_splitter=None,
            hovered_splitter_rect=None,
            hovered_inspector_field_key=None,
            hovered_inspector_field_rect=None,
            hovered_entity_id=None,
            hovered_entity_rect=None,
            block_ui=False,
        )

        assert len(result) == 1
        assert result[0].kind == HoverHighlightKind.TOPBAR_CONTROL
        assert result[0].label == "Maximize Viewport"
        assert result[0].rect.left == controls.toggle_max.left
        assert result[0].rect.bottom == controls.toggle_max.bottom
        assert result[0].rect.w == controls.toggle_max.width
        assert result[0].rect.h == controls.toggle_max.height

    def test_top_bar_control_blocked(self) -> None:
        """Test top bar hover blocked when block_ui=True."""
        result = resolve_hover_highlights(
            window_w=1280,
            window_h=720,
            hovered_menu_title=None,
            hovered_menu_title_rect=None,
            hovered_menu_item_id=None,
            hovered_menu_item_rect=None,
            hovered_top_bar_control_id="L",
            hovered_context_item_id=None,
            hovered_context_item_rect=None,
            hovered_dock_tab=None,
            hovered_dock_tab_rect=None,
            hovered_splitter=None,
            hovered_splitter_rect=None,
            hovered_inspector_field_key=None,
            hovered_inspector_field_rect=None,
            hovered_entity_id=None,
            hovered_entity_rect=None,
            block_ui=True,
        )
        assert result == ()

    def test_context_menu_item_highlight(self) -> None:
        """Test context menu item hover produces correct spec."""
        result = resolve_hover_highlights(
            window_w=1280,
            window_h=720,
            hovered_menu_title=None,
            hovered_menu_title_rect=None,
            hovered_menu_item_id=None,
            hovered_menu_item_rect=None,
            hovered_top_bar_control_id=None,
            hovered_context_item_id="delete_entity",
            hovered_context_item_rect=(300, 400, 150, 25),
            hovered_dock_tab=None,
            hovered_dock_tab_rect=None,
            hovered_splitter=None,
            hovered_splitter_rect=None,
            hovered_inspector_field_key=None,
            hovered_inspector_field_rect=None,
            hovered_entity_id=None,
            hovered_entity_rect=None,
            block_ui=False,
        )
        assert len(result) == 1
        assert result[0].kind == HoverHighlightKind.CONTEXT_ITEM
        assert result[0].label == "delete_entity"

    def test_dock_tab_highlight(self) -> None:
        """Test dock tab hover produces correct spec."""
        result = resolve_hover_highlights(
            window_w=1280,
            window_h=720,
            hovered_menu_title=None,
            hovered_menu_title_rect=None,
            hovered_menu_item_id=None,
            hovered_menu_item_rect=None,
            hovered_top_bar_control_id=None,
            hovered_context_item_id=None,
            hovered_context_item_rect=None,
            hovered_dock_tab=("left", "Hierarchy"),
            hovered_dock_tab_rect=(0, 600, 100, 25),
            hovered_splitter=None,
            hovered_splitter_rect=None,
            hovered_inspector_field_key=None,
            hovered_inspector_field_rect=None,
            hovered_entity_id=None,
            hovered_entity_rect=None,
            block_ui=False,
        )
        assert len(result) == 1
        assert result[0].kind == HoverHighlightKind.DOCK_TAB
        assert result[0].label == "left_Hierarchy"

    def test_splitter_highlight(self) -> None:
        """Test splitter hover produces correct spec."""
        result = resolve_hover_highlights(
            window_w=1280,
            window_h=720,
            hovered_menu_title=None,
            hovered_menu_title_rect=None,
            hovered_menu_item_id=None,
            hovered_menu_item_rect=None,
            hovered_top_bar_control_id=None,
            hovered_context_item_id=None,
            hovered_context_item_rect=None,
            hovered_dock_tab=None,
            hovered_dock_tab_rect=None,
            hovered_splitter="left",
            hovered_splitter_rect=(248, 25, 4, 670),
            hovered_inspector_field_key=None,
            hovered_inspector_field_rect=None,
            hovered_entity_id=None,
            hovered_entity_rect=None,
            block_ui=False,
        )
        assert len(result) == 1
        assert result[0].kind == HoverHighlightKind.SPLITTER
        assert result[0].label == "left_splitter"

    def test_inspector_field_highlight(self) -> None:
        """Test inspector field hover produces correct spec."""
        result = resolve_hover_highlights(
            window_w=1280,
            window_h=720,
            hovered_menu_title=None,
            hovered_menu_title_rect=None,
            hovered_menu_item_id=None,
            hovered_menu_item_rect=None,
            hovered_top_bar_control_id=None,
            hovered_context_item_id=None,
            hovered_context_item_rect=None,
            hovered_dock_tab=None,
            hovered_dock_tab_rect=None,
            hovered_splitter=None,
            hovered_splitter_rect=None,
            hovered_inspector_field_key="position.x",
            hovered_inspector_field_rect=(1100, 500, 150, 20),
            hovered_entity_id=None,
            hovered_entity_rect=None,
            block_ui=False,
        )
        assert len(result) == 1
        assert result[0].kind == HoverHighlightKind.INSPECTOR_FIELD
        assert result[0].label == "position.x"

    def test_entity_hover_highlight(self) -> None:
        """Test entity hover produces correct spec with world space flag."""
        result = resolve_hover_highlights(
            window_w=1280,
            window_h=720,
            hovered_menu_title=None,
            hovered_menu_title_rect=None,
            hovered_menu_item_id=None,
            hovered_menu_item_rect=None,
            hovered_top_bar_control_id=None,
            hovered_context_item_id=None,
            hovered_context_item_rect=None,
            hovered_dock_tab=None,
            hovered_dock_tab_rect=None,
            hovered_splitter=None,
            hovered_splitter_rect=None,
            hovered_inspector_field_key=None,
            hovered_inspector_field_rect=None,
            hovered_entity_id="player_001",
            hovered_entity_rect=(500, 300, 32, 48),
            block_ui=False,
        )
        assert len(result) == 1
        assert result[0].kind == HoverHighlightKind.ENTITY_HOVER
        assert result[0].label == "player_001"
        assert result[0].is_world_space is True

    def test_priority_context_over_menu(self) -> None:
        """Test context menu has priority over menu bar."""
        result = resolve_hover_highlights(
            window_w=1280,
            window_h=720,
            hovered_menu_title="File",
            hovered_menu_title_rect=(10, 695, 50, 25),
            hovered_menu_item_id="file_save",
            hovered_menu_item_rect=(10, 650, 150, 25),
            hovered_top_bar_control_id=None,
            hovered_context_item_id="delete",
            hovered_context_item_rect=(300, 400, 150, 25),
            hovered_dock_tab=None,
            hovered_dock_tab_rect=None,
            hovered_splitter=None,
            hovered_splitter_rect=None,
            hovered_inspector_field_key=None,
            hovered_inspector_field_rect=None,
            hovered_entity_id=None,
            hovered_entity_rect=None,
            block_ui=False,
        )
        assert len(result) == 3
        assert result[0].kind == HoverHighlightKind.CONTEXT_ITEM
        assert result[1].kind == HoverHighlightKind.MENU_ITEM
        assert result[2].kind == HoverHighlightKind.MENU_TITLE

    def test_priority_menu_over_splitter(self) -> None:
        """Test menu items have priority over splitter."""
        result = resolve_hover_highlights(
            window_w=1280,
            window_h=720,
            hovered_menu_title=None,
            hovered_menu_title_rect=None,
            hovered_menu_item_id="file_open",
            hovered_menu_item_rect=(10, 650, 150, 25),
            hovered_top_bar_control_id=None,
            hovered_context_item_id=None,
            hovered_context_item_rect=None,
            hovered_dock_tab=None,
            hovered_dock_tab_rect=None,
            hovered_splitter="left",
            hovered_splitter_rect=(248, 25, 4, 670),
            hovered_inspector_field_key=None,
            hovered_inspector_field_rect=None,
            hovered_entity_id=None,
            hovered_entity_rect=None,
            block_ui=False,
        )
        assert len(result) == 2
        assert result[0].kind == HoverHighlightKind.MENU_ITEM
        assert result[1].kind == HoverHighlightKind.SPLITTER

    def test_priority_menu_over_top_bar(self) -> None:
        """Test menu items have priority over top bar controls."""
        result = resolve_hover_highlights(
            window_w=1280,
            window_h=720,
            hovered_menu_title=None,
            hovered_menu_title_rect=None,
            hovered_menu_item_id="file_open",
            hovered_menu_item_rect=(10, 650, 150, 25),
            hovered_top_bar_control_id="L",
            hovered_context_item_id=None,
            hovered_context_item_rect=None,
            hovered_dock_tab=None,
            hovered_dock_tab_rect=None,
            hovered_splitter=None,
            hovered_splitter_rect=None,
            hovered_inspector_field_key=None,
            hovered_inspector_field_rect=None,
            hovered_entity_id=None,
            hovered_entity_rect=None,
            block_ui=False,
        )
        assert len(result) == 2
        assert result[0].kind == HoverHighlightKind.MENU_ITEM
        assert result[1].kind == HoverHighlightKind.TOPBAR_CONTROL

    def test_priority_splitter_over_dock_tab(self) -> None:
        """Test splitter has priority over dock tab."""
        result = resolve_hover_highlights(
            window_w=1280,
            window_h=720,
            hovered_menu_title=None,
            hovered_menu_title_rect=None,
            hovered_menu_item_id=None,
            hovered_menu_item_rect=None,
            hovered_top_bar_control_id=None,
            hovered_context_item_id=None,
            hovered_context_item_rect=None,
            hovered_dock_tab=("right", "Inspector"),
            hovered_dock_tab_rect=(1030, 600, 100, 25),
            hovered_splitter="right",
            hovered_splitter_rect=(1028, 25, 4, 670),
            hovered_inspector_field_key=None,
            hovered_inspector_field_rect=None,
            hovered_entity_id=None,
            hovered_entity_rect=None,
            block_ui=False,
        )
        assert len(result) == 2
        assert result[0].kind == HoverHighlightKind.SPLITTER
        assert result[1].kind == HoverHighlightKind.DOCK_TAB

    def test_priority_dock_tab_over_inspector(self) -> None:
        """Test dock tab has priority over inspector field."""
        result = resolve_hover_highlights(
            window_w=1280,
            window_h=720,
            hovered_menu_title=None,
            hovered_menu_title_rect=None,
            hovered_menu_item_id=None,
            hovered_menu_item_rect=None,
            hovered_top_bar_control_id=None,
            hovered_context_item_id=None,
            hovered_context_item_rect=None,
            hovered_dock_tab=("right", "Inspector"),
            hovered_dock_tab_rect=(1030, 600, 100, 25),
            hovered_splitter=None,
            hovered_splitter_rect=None,
            hovered_inspector_field_key="position.y",
            hovered_inspector_field_rect=(1100, 500, 150, 20),
            hovered_entity_id=None,
            hovered_entity_rect=None,
            block_ui=False,
        )
        assert len(result) == 2
        assert result[0].kind == HoverHighlightKind.DOCK_TAB
        assert result[1].kind == HoverHighlightKind.INSPECTOR_FIELD

    def test_priority_inspector_over_entity(self) -> None:
        """Test inspector field has priority over entity hover."""
        result = resolve_hover_highlights(
            window_w=1280,
            window_h=720,
            hovered_menu_title=None,
            hovered_menu_title_rect=None,
            hovered_menu_item_id=None,
            hovered_menu_item_rect=None,
            hovered_top_bar_control_id=None,
            hovered_context_item_id=None,
            hovered_context_item_rect=None,
            hovered_dock_tab=None,
            hovered_dock_tab_rect=None,
            hovered_splitter=None,
            hovered_splitter_rect=None,
            hovered_inspector_field_key="sprite",
            hovered_inspector_field_rect=(1100, 500, 150, 20),
            hovered_entity_id="npc_001",
            hovered_entity_rect=(640, 360, 32, 32),
            block_ui=False,
        )
        assert len(result) == 2
        assert result[0].kind == HoverHighlightKind.INSPECTOR_FIELD
        assert result[1].kind == HoverHighlightKind.ENTITY_HOVER

    def test_all_kinds_priority_order(self) -> None:
        """Test full priority chain with all hover kinds."""
        result = resolve_hover_highlights(
            window_w=1280,
            window_h=720,
            hovered_menu_title="Edit",
            hovered_menu_title_rect=(60, 695, 50, 25),
            hovered_menu_item_id="editor.history.undo",
            hovered_menu_item_rect=(60, 650, 150, 25),
            hovered_top_bar_control_id="M",
            hovered_context_item_id="copy",
            hovered_context_item_rect=(400, 400, 150, 25),
            hovered_dock_tab=("left", "Palette"),
            hovered_dock_tab_rect=(0, 600, 80, 25),
            hovered_splitter="left",
            hovered_splitter_rect=(248, 25, 4, 670),
            hovered_inspector_field_key="scale.x",
            hovered_inspector_field_rect=(1100, 500, 150, 20),
            hovered_entity_id="enemy_01",
            hovered_entity_rect=(500, 200, 48, 48),
            block_ui=False,
        )
        # Expected order: context > menu_item > menu_title > topbar > splitter > dock_tab > inspector > entity
        assert len(result) == 8
        assert result[0].kind == HoverHighlightKind.CONTEXT_ITEM
        assert result[1].kind == HoverHighlightKind.MENU_ITEM
        assert result[2].kind == HoverHighlightKind.MENU_TITLE
        assert result[3].kind == HoverHighlightKind.TOPBAR_CONTROL
        assert result[4].kind == HoverHighlightKind.SPLITTER
        assert result[5].kind == HoverHighlightKind.DOCK_TAB
        assert result[6].kind == HoverHighlightKind.INSPECTOR_FIELD
        assert result[7].kind == HoverHighlightKind.ENTITY_HOVER

    def test_rect_clamping_applied(self) -> None:
        """Test that rects are clamped to window bounds."""
        result = resolve_hover_highlights(
            window_w=1280,
            window_h=720,
            hovered_menu_title="Window",
            hovered_menu_title_rect=(1250, 695, 100, 25),  # Overflows right
            hovered_menu_item_id=None,
            hovered_menu_item_rect=None,
            hovered_top_bar_control_id=None,
            hovered_context_item_id=None,
            hovered_context_item_rect=None,
            hovered_dock_tab=None,
            hovered_dock_tab_rect=None,
            hovered_splitter=None,
            hovered_splitter_rect=None,
            hovered_inspector_field_key=None,
            hovered_inspector_field_rect=None,
            hovered_entity_id=None,
            hovered_entity_rect=None,
            block_ui=False,
        )
        assert len(result) == 1
        assert result[0].rect.right == 1280  # Clamped

    def test_entity_rect_not_clamped(self) -> None:
        """Test that entity rects (world space) are not clamped."""
        result = resolve_hover_highlights(
            window_w=1280,
            window_h=720,
            hovered_menu_title=None,
            hovered_menu_title_rect=None,
            hovered_menu_item_id=None,
            hovered_menu_item_rect=None,
            hovered_top_bar_control_id=None,
            hovered_context_item_id=None,
            hovered_context_item_rect=None,
            hovered_dock_tab=None,
            hovered_dock_tab_rect=None,
            hovered_splitter=None,
            hovered_splitter_rect=None,
            hovered_inspector_field_key=None,
            hovered_inspector_field_rect=None,
            hovered_entity_id="far_entity",
            hovered_entity_rect=(5000, 3000, 64, 64),  # Far outside screen
            block_ui=False,
        )
        assert len(result) == 1
        # World coordinates should NOT be clamped
        assert result[0].rect.left == 5000
        assert result[0].rect.bottom == 3000

    def test_missing_rect_skips_highlight(self) -> None:
        """Test that missing rect results in no highlight."""
        result = resolve_hover_highlights(
            window_w=1280,
            window_h=720,
            hovered_menu_title="File",
            hovered_menu_title_rect=None,  # Missing rect
            hovered_menu_item_id=None,
            hovered_menu_item_rect=None,
            hovered_top_bar_control_id=None,
            hovered_context_item_id=None,
            hovered_context_item_rect=None,
            hovered_dock_tab=None,
            hovered_dock_tab_rect=None,
            hovered_splitter=None,
            hovered_splitter_rect=None,
            hovered_inspector_field_key=None,
            hovered_inspector_field_rect=None,
            hovered_entity_id=None,
            hovered_entity_rect=None,
            block_ui=False,
        )
        assert len(result) == 0


class TestIsUiBlocked:
    """Tests for is_ui_blocked function."""

    def test_not_blocked_default(self) -> None:
        """Test returns False for controller with no active modes."""
        controller = _make_controller()
        assert is_ui_blocked(controller) is False

    def test_blocked_palette_filter(self) -> None:
        """Test blocked when palette filter is active."""
        controller = _make_controller(palette_filter_active=True)
        assert is_ui_blocked(controller) is True

    def test_blocked_hierarchy_filter(self) -> None:
        """Test blocked when hierarchy filter is active."""
        controller = _make_controller(hierarchy_filter_active=True)
        assert is_ui_blocked(controller) is True

    def test_blocked_hierarchy_rename(self) -> None:
        """Test blocked when hierarchy rename is active."""
        controller = _make_controller(hierarchy_rename_active=True)
        assert is_ui_blocked(controller) is True

    def test_blocked_animation_edit(self) -> None:
        """Test blocked when animation edit is active."""
        controller = _make_controller(animation_edit_active=True)
        assert is_ui_blocked(controller) is True

    def test_blocked_inspector_edit(self) -> None:
        """Test blocked when inspector edit is active."""
        controller = _make_controller(inspector_edit_active=True)
        assert is_ui_blocked(controller) is True

    def test_blocked_command_palette(self) -> None:
        """Test blocked when command palette is active."""
        panels = SimpleNamespace(is_command_palette_open=lambda: True)
        controller = _make_controller(panels=panels)
        assert is_ui_blocked(controller) is True

    def test_blocked_unsaved_changes_modal(self) -> None:
        """Test blocked when unsaved changes modal is pending."""
        controller = _make_controller(_unsaved_changes_pending=True)
        assert is_ui_blocked(controller) is True

    def test_blocked_scene_browser(self) -> None:
        """Test blocked when scene browser is active."""
        controller = _make_controller(scene_browser_active=True)
        assert is_ui_blocked(controller) is True

    def test_blocked_entity_panels_filter(self) -> None:
        """Test blocked when entity panels filter is active."""
        controller = _make_controller(entity_panels_filter_active=True)
        assert is_ui_blocked(controller) is True

    def test_blocked_asset_browser_filter(self) -> None:
        """Test blocked when asset browser filter is active."""
        controller = _make_controller(asset_browser_filter_active=True)
        assert is_ui_blocked(controller) is True


class TestHoverHighlightKind:
    """Tests for HoverHighlightKind enum."""

    def test_all_kinds_exist(self) -> None:
        """Test all expected kinds are defined."""
        assert HoverHighlightKind.MENU_TITLE.value == "menu_title"
        assert HoverHighlightKind.MENU_ITEM.value == "menu_item"
        assert HoverHighlightKind.CONTEXT_ITEM.value == "context_item"
        assert HoverHighlightKind.TOPBAR_CONTROL.value == "topbar_control"
        assert HoverHighlightKind.DOCK_TAB.value == "dock_tab"
        assert HoverHighlightKind.SPLITTER.value == "splitter"
        assert HoverHighlightKind.INSPECTOR_FIELD.value == "inspector_field"
        assert HoverHighlightKind.ENTITY_HOVER.value == "entity_hover"

    def test_kind_count(self) -> None:
        """Test expected number of kinds."""
        assert len(HoverHighlightKind) == 8

    def test_kind_is_string_enum(self) -> None:
        """Test that kind values are strings."""
        for kind in HoverHighlightKind:
            assert isinstance(kind.value, str)
