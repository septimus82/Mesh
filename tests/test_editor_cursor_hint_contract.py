"""Contract tests for editor_cursor_model module.

Tests cursor hint computation as pure functions - headless, no arcade dependency.
"""

from __future__ import annotations

import pytest

from engine.editor.editor_cursor_model import (
    CursorHintResult,
    build_cursor_hint,
)
from tests._typing import as_any


# -----------------------------------------------------------------------------
# CursorHintResult dataclass
# -----------------------------------------------------------------------------


class TestCursorHintResult:
    """Tests for CursorHintResult dataclass."""

    def test_with_text_and_kind(self) -> None:
        result = CursorHintResult(text="Test hint", kind="test")
        assert result.text == "Test hint"
        assert result.kind == "test"

    def test_with_none_values(self) -> None:
        result = CursorHintResult(text=None, kind=None)
        assert result.text is None
        assert result.kind is None

    def test_frozen(self) -> None:
        result = CursorHintResult(text="Hint", kind="type")
        with pytest.raises(AttributeError):
            as_any(result).text = "changed"

    def test_equality(self) -> None:
        a = CursorHintResult(text="Hint", kind="type")
        b = CursorHintResult(text="Hint", kind="type")
        assert a == b

    def test_inequality(self) -> None:
        a = CursorHintResult(text="Hint A", kind="type")
        b = CursorHintResult(text="Hint B", kind="type")
        assert a != b


# -----------------------------------------------------------------------------
# build_cursor_hint - editor inactive
# -----------------------------------------------------------------------------


class TestBuildCursorHintEditorInactive:
    """Tests for build_cursor_hint when editor is inactive."""

    def test_returns_none_when_editor_inactive(self) -> None:
        result = build_cursor_hint(
            editor_active=False,
            mouse_x=100.0,
            mouse_y=100.0,
            window_w=1280,
            window_h=720,
            ui_blocked=False,
            ui_hover=False,
            marquee_active=True,  # Should be ignored
            alt_dup_active=True,  # Should be ignored
            gizmo_drag_active=True,  # Should be ignored
            gizmo_mode="move",
            shell_layout=None,
            splitter_hit="left",  # Should be ignored
            entity_hit=True,  # Should be ignored
        )
        assert result.text is None
        assert result.kind is None


# -----------------------------------------------------------------------------
# build_cursor_hint - priority order
# -----------------------------------------------------------------------------


class TestBuildCursorHintPriority:
    """Tests for build_cursor_hint priority order."""

    def _base_kwargs(self) -> dict:
        """Return base kwargs with editor active and no hints."""
        return {
            "editor_active": True,
            "mouse_x": 400.0,
            "mouse_y": 300.0,
            "window_w": 1280,
            "window_h": 720,
            "ui_blocked": False,
            "ui_hover": False,
            "marquee_active": False,
            "alt_dup_active": False,
            "gizmo_drag_active": False,
            "gizmo_mode": None,
            "shell_layout": None,
            "splitter_hit": None,
            "entity_hit": False,
        }

    def test_no_hints_returns_default(self) -> None:
        result = build_cursor_hint(**self._base_kwargs())
        assert result.text is None
        assert result.kind == "default"

    def test_priority_1_marquee(self) -> None:
        """Marquee should have highest priority."""
        kwargs = self._base_kwargs()
        kwargs["marquee_active"] = True
        kwargs["alt_dup_active"] = True
        kwargs["gizmo_drag_active"] = True
        kwargs["gizmo_mode"] = "move"
        kwargs["splitter_hit"] = "left"
        kwargs["entity_hit"] = True
        result = build_cursor_hint(**kwargs)
        assert result.kind == "crosshair"
        assert "Marquee" in result.text

    def test_priority_2_alt_dup(self) -> None:
        """Alt-dup should override gizmo, splitter, entity."""
        kwargs = self._base_kwargs()
        kwargs["alt_dup_active"] = True
        kwargs["gizmo_drag_active"] = True
        kwargs["gizmo_mode"] = "move"
        kwargs["splitter_hit"] = "left"
        kwargs["entity_hit"] = True
        result = build_cursor_hint(**kwargs)
        assert result.kind == "move"
        assert "Alt-dup" in result.text

    def test_priority_3_gizmo_drag(self) -> None:
        """Gizmo drag should override splitter and entity."""
        kwargs = self._base_kwargs()
        kwargs["gizmo_drag_active"] = True
        kwargs["gizmo_mode"] = "move"
        kwargs["splitter_hit"] = "left"
        kwargs["entity_hit"] = True
        result = build_cursor_hint(**kwargs)
        assert result.kind == "move"
        assert "Move" in result.text

    def test_priority_4_splitter_hit(self) -> None:
        """Splitter hit should override entity."""
        kwargs = self._base_kwargs()
        kwargs["splitter_hit"] = "left"
        kwargs["entity_hit"] = True
        result = build_cursor_hint(**kwargs)
        assert result.kind == "resize_h"
        assert "Resize" in result.text

    def test_priority_5_entity_hit(self) -> None:
        """Entity hit should be lowest priority."""
        kwargs = self._base_kwargs()
        kwargs["entity_hit"] = True
        result = build_cursor_hint(**kwargs)
        assert result.kind == "move"
        assert "Drag" in result.text


# -----------------------------------------------------------------------------
# build_cursor_hint - marquee
# -----------------------------------------------------------------------------


class TestBuildCursorHintMarquee:
    """Tests for marquee cursor hint."""

    def test_marquee_text_includes_escape_hint(self) -> None:
        result = build_cursor_hint(
            editor_active=True,
            mouse_x=400.0,
            mouse_y=300.0,
            window_w=1280,
            window_h=720,
            ui_blocked=False,
            ui_hover=False,
            marquee_active=True,
            alt_dup_active=False,
            gizmo_drag_active=False,
            gizmo_mode=None,
            shell_layout=None,
            splitter_hit=None,
            entity_hit=False,
        )
        assert "Esc" in result.text or "cancel" in result.text.lower()


# -----------------------------------------------------------------------------
# build_cursor_hint - alt-dup
# -----------------------------------------------------------------------------


class TestBuildCursorHintAltDup:
    """Tests for alt-drag duplicate cursor hint."""

    def test_alt_dup_text_includes_cancel_hint(self) -> None:
        result = build_cursor_hint(
            editor_active=True,
            mouse_x=400.0,
            mouse_y=300.0,
            window_w=1280,
            window_h=720,
            ui_blocked=False,
            ui_hover=False,
            marquee_active=False,
            alt_dup_active=True,
            gizmo_drag_active=False,
            gizmo_mode=None,
            shell_layout=None,
            splitter_hit=None,
            entity_hit=False,
        )
        assert "cancel" in result.text.lower() or "RMB" in result.text or "Esc" in result.text


# -----------------------------------------------------------------------------
# build_cursor_hint - gizmo modes
# -----------------------------------------------------------------------------


class TestBuildCursorHintGizmoModes:
    """Tests for gizmo drag cursor hints."""

    def test_move_mode(self) -> None:
        result = build_cursor_hint(
            editor_active=True,
            mouse_x=400.0,
            mouse_y=300.0,
            window_w=1280,
            window_h=720,
            ui_blocked=False,
            ui_hover=False,
            marquee_active=False,
            alt_dup_active=False,
            gizmo_drag_active=True,
            gizmo_mode="move",
            shell_layout=None,
            splitter_hit=None,
            entity_hit=False,
        )
        assert result.kind == "move"
        assert "Move" in result.text

    def test_rotate_mode(self) -> None:
        result = build_cursor_hint(
            editor_active=True,
            mouse_x=400.0,
            mouse_y=300.0,
            window_w=1280,
            window_h=720,
            ui_blocked=False,
            ui_hover=False,
            marquee_active=False,
            alt_dup_active=False,
            gizmo_drag_active=True,
            gizmo_mode="rotate",
            shell_layout=None,
            splitter_hit=None,
            entity_hit=False,
        )
        assert result.kind == "move"
        assert "Rotate" in result.text

    def test_scale_mode(self) -> None:
        result = build_cursor_hint(
            editor_active=True,
            mouse_x=400.0,
            mouse_y=300.0,
            window_w=1280,
            window_h=720,
            ui_blocked=False,
            ui_hover=False,
            marquee_active=False,
            alt_dup_active=False,
            gizmo_drag_active=True,
            gizmo_mode="scale",
            shell_layout=None,
            splitter_hit=None,
            entity_hit=False,
        )
        assert result.kind == "move"
        assert "Scale" in result.text

    def test_gizmo_drag_without_mode_returns_default(self) -> None:
        """Gizmo drag without mode should fall back to default."""
        result = build_cursor_hint(
            editor_active=True,
            mouse_x=400.0,
            mouse_y=300.0,
            window_w=1280,
            window_h=720,
            ui_blocked=False,
            ui_hover=False,
            marquee_active=False,
            alt_dup_active=False,
            gizmo_drag_active=True,
            gizmo_mode=None,
            shell_layout=None,
            splitter_hit=None,
            entity_hit=False,
        )
        # With gizmo_mode=None, gizmo drag check fails, falls through
        assert result.kind == "default"


# -----------------------------------------------------------------------------
# build_cursor_hint - splitter hit
# -----------------------------------------------------------------------------


class TestBuildCursorHintSplitter:
    """Tests for splitter hover cursor hint."""

    def test_left_splitter(self) -> None:
        result = build_cursor_hint(
            editor_active=True,
            mouse_x=200.0,
            mouse_y=300.0,
            window_w=1280,
            window_h=720,
            ui_blocked=False,
            ui_hover=False,
            marquee_active=False,
            alt_dup_active=False,
            gizmo_drag_active=False,
            gizmo_mode=None,
            shell_layout=None,
            splitter_hit="left",
            entity_hit=False,
        )
        assert result.kind == "resize_h"
        assert "Resize" in result.text

    def test_right_splitter(self) -> None:
        result = build_cursor_hint(
            editor_active=True,
            mouse_x=1100.0,
            mouse_y=300.0,
            window_w=1280,
            window_h=720,
            ui_blocked=False,
            ui_hover=False,
            marquee_active=False,
            alt_dup_active=False,
            gizmo_drag_active=False,
            gizmo_mode=None,
            shell_layout=None,
            splitter_hit="right",
            entity_hit=False,
        )
        assert result.kind == "resize_h"
        assert "Resize" in result.text


# -----------------------------------------------------------------------------
# build_cursor_hint - entity hit
# -----------------------------------------------------------------------------


class TestBuildCursorHintEntity:
    """Tests for entity hover cursor hint."""

    def test_entity_hit_returns_drag_hint(self) -> None:
        result = build_cursor_hint(
            editor_active=True,
            mouse_x=640.0,
            mouse_y=360.0,
            window_w=1280,
            window_h=720,
            ui_blocked=False,
            ui_hover=False,
            marquee_active=False,
            alt_dup_active=False,
            gizmo_drag_active=False,
            gizmo_mode=None,
            shell_layout=None,
            splitter_hit=None,
            entity_hit=True,
        )
        assert result.kind == "move"
        assert "Drag" in result.text or "Entity" in result.text


# -----------------------------------------------------------------------------
# build_cursor_hint - UI hover and blocked
# -----------------------------------------------------------------------------


class TestBuildCursorHintUiHover:
    """Tests for UI hover cursor hint."""

    def test_ui_hover_returns_pointer(self) -> None:
        result = build_cursor_hint(
            editor_active=True,
            mouse_x=100.0,
            mouse_y=100.0,
            window_w=1280,
            window_h=720,
            ui_blocked=False,
            ui_hover=True,
            marquee_active=False,
            alt_dup_active=False,
            gizmo_drag_active=False,
            gizmo_mode=None,
            shell_layout=None,
            splitter_hit=None,
            entity_hit=False,
        )
        assert result.text is None
        assert result.kind == "pointer"

    def test_ui_blocked_returns_default(self) -> None:
        result = build_cursor_hint(
            editor_active=True,
            mouse_x=100.0,
            mouse_y=100.0,
            window_w=1280,
            window_h=720,
            ui_blocked=True,
            ui_hover=True,
            marquee_active=True,
            alt_dup_active=True,
            gizmo_drag_active=True,
            gizmo_mode="move",
            shell_layout=None,
            splitter_hit="left",
            entity_hit=True,
        )
        assert result.text is None
        assert result.kind == "default"
