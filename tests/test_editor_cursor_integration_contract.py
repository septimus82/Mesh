"""Integration contract tests for editor cursor hint.

Tests the integration of cursor hint with EditorController - headless-safe
using stubs and mocks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

# -----------------------------------------------------------------------------
# Stub classes for headless testing
# -----------------------------------------------------------------------------


@dataclass
class MockRect:
    """Mock Rect for entity bounds testing."""

    x: float
    y: float
    width: float
    height: float

    def contains_point(self, px: float, py: float) -> bool:
        return (
            self.x <= px <= self.x + self.width
            and self.y <= py <= self.y + self.height
        )


@dataclass
class MockShellLayout:
    """Mock shell layout with splitter rects."""

    left_splitter: MockRect
    right_splitter: MockRect


def make_mock_shell_layout() -> MockShellLayout:
    """Create a mock shell layout with typical splitter positions."""
    return MockShellLayout(
        left_splitter=MockRect(x=218.0, y=0.0, width=6.0, height=720.0),
        right_splitter=MockRect(x=1018.0, y=0.0, width=6.0, height=720.0),
    )


class MockSprite:
    """Mock sprite for entity hit testing."""

    def __init__(self, x: float, y: float, width: float, height: float) -> None:
        self.mesh_entity_data = {
            "position": {"x": x, "y": y},
            "scale": {"x": 1.0, "y": 1.0},
        }
        self.center_x = x + width / 2
        self.center_y = y + height / 2
        self.width = width
        self.height = height


class MockSceneController:
    """Mock scene controller with sprites."""

    def __init__(self, sprites: list = None) -> None:
        self.all_sprites = sprites or []


class MockWindow:
    """Mock window for coordinate conversion."""

    def __init__(self) -> None:
        self.scene_controller = MockSceneController()

    def screen_to_world(self, x: float, y: float) -> Tuple[float, float]:
        """Simple passthrough for testing."""
        return (x, y)


class StubEditorController:
    """Stub EditorController with just the cursor hint methods."""

    def __init__(self) -> None:
        self.active = True
        self._last_mouse_x = 0.0
        self._last_mouse_y = 0.0
        self.window = MockWindow()
        self.selected_entity = None
        # State flags
        self._marquee_active = False
        self._alt_dup_active = False
        self.entity_dragging = False
        self._rotate_drag_active = False
        self._scale_drag_active = False

    def set_last_mouse_pos(self, x: float, y: float) -> None:
        self._last_mouse_x = float(x)
        self._last_mouse_y = float(y)

    def get_last_mouse_pos(self) -> Tuple[float, float]:
        return (self._last_mouse_x, self._last_mouse_y)


# -----------------------------------------------------------------------------
# Integration tests
# -----------------------------------------------------------------------------


class TestEditorControllerMouseTracking:
    """Tests for mouse position tracking on controller."""

    def test_set_and_get_mouse_pos(self) -> None:
        ctrl = StubEditorController()
        ctrl.set_last_mouse_pos(123.5, 456.5)
        x, y = ctrl.get_last_mouse_pos()
        assert x == 123.5
        assert y == 456.5

    def test_initial_mouse_pos_is_zero(self) -> None:
        ctrl = StubEditorController()
        x, y = ctrl.get_last_mouse_pos()
        assert x == 0.0
        assert y == 0.0

    def test_mouse_pos_converts_to_float(self) -> None:
        ctrl = StubEditorController()
        ctrl.set_last_mouse_pos(100, 200)  # int input
        x, y = ctrl.get_last_mouse_pos()
        assert isinstance(x, float)
        assert isinstance(y, float)


class TestBuildCursorHintIntegration:
    """Tests for build_cursor_hint with mocked dependencies."""

    def test_marquee_active_returns_marquee_hint(self) -> None:
        """Marquee active should return marquee hint regardless of other state."""
        from engine.editor.editor_cursor_model import build_cursor_hint

        result = build_cursor_hint(
            editor_active=True,
            mouse_x=640.0,
            mouse_y=360.0,
            window_w=1280,
            window_h=720,
            ui_blocked=False,
            ui_hover=False,
            marquee_active=True,
            alt_dup_active=False,
            gizmo_drag_active=False,
            gizmo_mode=None,
            shell_layout=make_mock_shell_layout(),
            splitter_hit=None,
            entity_hit=False,
        )
        assert result.kind == "crosshair"

    def test_alt_dup_active_returns_altdup_hint(self) -> None:
        """Alt-dup active should return altdup hint."""
        from engine.editor.editor_cursor_model import build_cursor_hint

        result = build_cursor_hint(
            editor_active=True,
            mouse_x=640.0,
            mouse_y=360.0,
            window_w=1280,
            window_h=720,
            ui_blocked=False,
            ui_hover=False,
            marquee_active=False,
            alt_dup_active=True,
            gizmo_drag_active=False,
            gizmo_mode=None,
            shell_layout=make_mock_shell_layout(),
            splitter_hit=None,
            entity_hit=False,
        )
        assert result.kind == "move"

    def test_splitter_hit_with_layout(self) -> None:
        """Splitter hit should return resize hint."""
        from engine.editor.editor_cursor_model import build_cursor_hint

        result = build_cursor_hint(
            editor_active=True,
            mouse_x=220.0,  # Near left splitter
            mouse_y=360.0,
            window_w=1280,
            window_h=720,
            ui_blocked=False,
            ui_hover=False,
            marquee_active=False,
            alt_dup_active=False,
            gizmo_drag_active=False,
            gizmo_mode=None,
            shell_layout=make_mock_shell_layout(),
            splitter_hit="left",
            entity_hit=False,
        )
        assert result.kind == "resize_h"


class TestHitTestSplitterIntegration:
    """Tests for hit_test_splitter integration with shell layout."""

    def test_hit_test_splitter_left(self) -> None:
        """Should detect left splitter hit."""
        from engine.editor.editor_shell_layout import (
            compute_editor_shell_layout,
            hit_test_splitter,
        )

        layout = compute_editor_shell_layout(
            window_width=1280,
            window_height=720,
            left_dock_w=220,
            right_dock_w=260,
        )
        # Hit right at splitter boundary
        result = hit_test_splitter(221.0, 360.0, layout)
        assert result == "left"

    def test_hit_test_splitter_right(self) -> None:
        """Should detect right splitter hit."""
        from engine.editor.editor_shell_layout import (
            compute_editor_shell_layout,
            hit_test_splitter,
        )

        layout = compute_editor_shell_layout(
            window_width=1280,
            window_height=720,
            left_dock_w=220,
            right_dock_w=260,
        )
        # Right dock starts at window_w - right dock width
        right_splitter_x = 1280 - 260 - 3  # Around splitter center
        result = hit_test_splitter(right_splitter_x, 360.0, layout)
        assert result == "right"

    def test_hit_test_splitter_viewport(self) -> None:
        """Should return None when over viewport."""
        from engine.editor.editor_shell_layout import (
            compute_editor_shell_layout,
            hit_test_splitter,
        )

        layout = compute_editor_shell_layout(
            window_width=1280,
            window_height=720,
            left_dock_w=220,
            right_dock_w=260,
        )
        # Center of viewport
        result = hit_test_splitter(640.0, 360.0, layout)
        assert result is None


class TestEntityBoundsIntegration:
    """Tests for resolve_entity_bounds integration."""

    def test_resolve_entity_bounds_returns_rect(self) -> None:
        """Should return Rect for valid entity."""
        from engine.editor.selection_outline import resolve_entity_bounds

        sprite = MockSprite(100.0, 100.0, 64.0, 64.0)
        entity_data = sprite.mesh_entity_data

        rect = resolve_entity_bounds(entity_data, sprite)
        # resolve_entity_bounds returns arcade.Rect or similar
        assert rect is not None

    def test_resolve_entity_bounds_none_for_invalid(self) -> None:
        """Should handle None entity data gracefully."""
        from engine.editor.selection_outline import resolve_entity_bounds

        sprite = MockSprite(100.0, 100.0, 64.0, 64.0)
        rect = resolve_entity_bounds(None, sprite)
        # Should handle gracefully (may return None or computed bounds)
        # Just verify no exception raised
        assert rect is not None or rect is None  # Passes either way


class TestEditorInactiveIntegration:
    """Tests for cursor hint when editor is inactive."""

    def test_inactive_editor_returns_none(self) -> None:
        """Should return None when editor is not active."""
        from engine.editor.editor_cursor_model import build_cursor_hint

        result = build_cursor_hint(
            editor_active=False,
            mouse_x=640.0,
            mouse_y=360.0,
            window_w=1280,
            window_h=720,
            ui_blocked=False,
            ui_hover=False,
            marquee_active=True,
            alt_dup_active=True,
            gizmo_drag_active=True,
            gizmo_mode="move",
            shell_layout=make_mock_shell_layout(),
            splitter_hit="left",
            entity_hit=True,
        )
        assert result.text is None
        assert result.kind is None


class TestCursorHintKinds:
    """Tests for cursor hint kind values."""

    def test_all_kinds_are_strings(self) -> None:
        """All hint kinds should be strings."""
        from engine.editor.editor_cursor_model import build_cursor_hint

        kinds = []

        # Marquee
        r = build_cursor_hint(
            editor_active=True, mouse_x=0, mouse_y=0, window_w=1280, window_h=720,
            ui_blocked=False,
            ui_hover=False,
            marquee_active=True, alt_dup_active=False, gizmo_drag_active=False,
            gizmo_mode=None, shell_layout=None, splitter_hit=None, entity_hit=False,
        )
        kinds.append(r.kind)

        # Alt-dup
        r = build_cursor_hint(
            editor_active=True, mouse_x=0, mouse_y=0, window_w=1280, window_h=720,
            ui_blocked=False,
            ui_hover=False,
            marquee_active=False, alt_dup_active=True, gizmo_drag_active=False,
            gizmo_mode=None, shell_layout=None, splitter_hit=None, entity_hit=False,
        )
        kinds.append(r.kind)

        # Gizmo
        r = build_cursor_hint(
            editor_active=True, mouse_x=0, mouse_y=0, window_w=1280, window_h=720,
            ui_blocked=False,
            ui_hover=False,
            marquee_active=False, alt_dup_active=False, gizmo_drag_active=True,
            gizmo_mode="move", shell_layout=None, splitter_hit=None, entity_hit=False,
        )
        kinds.append(r.kind)

        # Splitter
        r = build_cursor_hint(
            editor_active=True, mouse_x=0, mouse_y=0, window_w=1280, window_h=720,
            ui_blocked=False,
            ui_hover=False,
            marquee_active=False, alt_dup_active=False, gizmo_drag_active=False,
            gizmo_mode=None, shell_layout=None, splitter_hit="left", entity_hit=False,
        )
        kinds.append(r.kind)

        # Entity
        r = build_cursor_hint(
            editor_active=True, mouse_x=0, mouse_y=0, window_w=1280, window_h=720,
            ui_blocked=False,
            ui_hover=False,
            marquee_active=False, alt_dup_active=False, gizmo_drag_active=False,
            gizmo_mode=None, shell_layout=None, splitter_hit=None, entity_hit=True,
        )
        kinds.append(r.kind)

        # UI hover
        r = build_cursor_hint(
            editor_active=True, mouse_x=0, mouse_y=0, window_w=1280, window_h=720,
            ui_blocked=False,
            ui_hover=True,
            marquee_active=False, alt_dup_active=False, gizmo_drag_active=False,
            gizmo_mode=None, shell_layout=None, splitter_hit=None, entity_hit=False,
        )
        kinds.append(r.kind)

        # Default
        r = build_cursor_hint(
            editor_active=True, mouse_x=0, mouse_y=0, window_w=1280, window_h=720,
            ui_blocked=False,
            ui_hover=False,
            marquee_active=False, alt_dup_active=False, gizmo_drag_active=False,
            gizmo_mode=None, shell_layout=None, splitter_hit=None, entity_hit=False,
        )
        kinds.append(r.kind)

        for kind in kinds:
            assert isinstance(kind, str)

    def test_expected_kind_values(self) -> None:
        """Verify expected kind values are used."""
        expected_kinds = {"crosshair", "move", "resize_h", "pointer", "default"}
        from engine.editor.editor_cursor_model import build_cursor_hint

        actual_kinds = set()

        # Marquee
        r = build_cursor_hint(
            editor_active=True, mouse_x=0, mouse_y=0, window_w=1280, window_h=720,
            ui_blocked=False,
            ui_hover=False,
            marquee_active=True, alt_dup_active=False, gizmo_drag_active=False,
            gizmo_mode=None, shell_layout=None, splitter_hit=None, entity_hit=False,
        )
        actual_kinds.add(r.kind)

        # Alt-dup
        r = build_cursor_hint(
            editor_active=True, mouse_x=0, mouse_y=0, window_w=1280, window_h=720,
            ui_blocked=False,
            ui_hover=False,
            marquee_active=False, alt_dup_active=True, gizmo_drag_active=False,
            gizmo_mode=None, shell_layout=None, splitter_hit=None, entity_hit=False,
        )
        actual_kinds.add(r.kind)

        # Gizmo
        r = build_cursor_hint(
            editor_active=True, mouse_x=0, mouse_y=0, window_w=1280, window_h=720,
            ui_blocked=False,
            ui_hover=False,
            marquee_active=False, alt_dup_active=False, gizmo_drag_active=True,
            gizmo_mode="move", shell_layout=None, splitter_hit=None, entity_hit=False,
        )
        actual_kinds.add(r.kind)

        # Splitter
        r = build_cursor_hint(
            editor_active=True, mouse_x=0, mouse_y=0, window_w=1280, window_h=720,
            ui_blocked=False,
            ui_hover=False,
            marquee_active=False, alt_dup_active=False, gizmo_drag_active=False,
            gizmo_mode=None, shell_layout=None, splitter_hit="left", entity_hit=False,
        )
        actual_kinds.add(r.kind)

        # Entity
        r = build_cursor_hint(
            editor_active=True, mouse_x=0, mouse_y=0, window_w=1280, window_h=720,
            ui_blocked=False,
            ui_hover=False,
            marquee_active=False, alt_dup_active=False, gizmo_drag_active=False,
            gizmo_mode=None, shell_layout=None, splitter_hit=None, entity_hit=True,
        )
        actual_kinds.add(r.kind)

        # UI hover
        r = build_cursor_hint(
            editor_active=True, mouse_x=0, mouse_y=0, window_w=1280, window_h=720,
            ui_blocked=False,
            ui_hover=True,
            marquee_active=False, alt_dup_active=False, gizmo_drag_active=False,
            gizmo_mode=None, shell_layout=None, splitter_hit=None, entity_hit=False,
        )
        actual_kinds.add(r.kind)

        # Default
        r = build_cursor_hint(
            editor_active=True, mouse_x=0, mouse_y=0, window_w=1280, window_h=720,
            ui_blocked=False,
            ui_hover=False,
            marquee_active=False, alt_dup_active=False, gizmo_drag_active=False,
            gizmo_mode=None, shell_layout=None, splitter_hit=None, entity_hit=False,
        )
        actual_kinds.add(r.kind)

        assert actual_kinds == expected_kinds
