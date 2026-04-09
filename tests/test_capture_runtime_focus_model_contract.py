"""Contract tests for capture_runtime_focus_model.

Tests verify:
1. SCOPE_* constants are strings
2. compute_active_scopes returns ordered list of active scopes
3. Scope priority ordering is correct
"""
from __future__ import annotations

import pytest

from engine.input_runtime.capture_runtime_focus_model import (
    SCOPE_CAPTURE_MODE,
    SCOPE_COMMAND_PALETTE,
    SCOPE_CONFIRM_MODAL,
    SCOPE_CONSOLE,
    SCOPE_CONTEXT_MENU,
    SCOPE_AUTHORING_SELECTED,
    SCOPE_ENTITY_PAINT,
    SCOPE_ENTITY_SELECT,
    SCOPE_GLOBAL,
    SCOPE_INLINE_RENAME,
    SCOPE_KEYBINDS,
    SCOPE_PALETTE_MODE,
    SCOPE_PROBLEMS,
    SCOPE_PROJECT_EXPLORER,
    SCOPE_TILE_PAINT,
    SCOPE_PRIORITY,
    CaptureFocusSnapshot,
    compute_active_scopes,
)
from tests._typing import as_any


def _make_snapshot(**overrides) -> CaptureFocusSnapshot:
    """Helper to create snapshot with defaults."""
    defaults = {
        "is_confirm_modal_open": False,
        "is_context_menu_open": False,
        "is_keybinds_recording": False,
        "is_keybinds_open": False,
        "is_inline_rename_active": False,
        "is_command_palette_open": False,
        "is_command_palette_prompt_active": False,
        "is_console_active": False,
        "is_project_explorer_focused": False,
        "is_problems_focused": False,
        "is_palette_mode_enabled": False,
        "is_capture_mode_enabled": False,
        "is_tile_paint_enabled": False,
        "is_entity_paint_enabled": False,
        "is_entity_select_active": False,
        "is_authoring_selected": False,
        "show_debug": False,
        "editor_active": False,
        "ui_blocked": False,
        "scene_persist_armed": False,
        "ctrl": False,
        "alt": False,
        "shift": False,
    }
    defaults.update(overrides)
    return CaptureFocusSnapshot(**defaults)


class TestScopeConstants:
    """Test scope constant definitions."""

    def test_all_scope_constants_are_strings(self) -> None:
        """All SCOPE_* constants must be strings."""
        scopes = [
            SCOPE_CONFIRM_MODAL,
            SCOPE_CONTEXT_MENU,
            SCOPE_KEYBINDS,
            SCOPE_INLINE_RENAME,
            SCOPE_COMMAND_PALETTE,
            SCOPE_CONSOLE,
            SCOPE_PROJECT_EXPLORER,
            SCOPE_PROBLEMS,
            SCOPE_PALETTE_MODE,
            SCOPE_CAPTURE_MODE,
            SCOPE_TILE_PAINT,
            SCOPE_ENTITY_PAINT,
            SCOPE_ENTITY_SELECT,
            SCOPE_AUTHORING_SELECTED,
            SCOPE_GLOBAL,
        ]
        for scope in scopes:
            assert isinstance(scope, str), f"Scope {scope!r} is not a string"
            assert scope, "Scope constant is empty"

    def test_scope_constants_are_unique(self) -> None:
        """All scope constants must have unique values."""
        scopes = [
            SCOPE_CONFIRM_MODAL,
            SCOPE_CONTEXT_MENU,
            SCOPE_KEYBINDS,
            SCOPE_INLINE_RENAME,
            SCOPE_COMMAND_PALETTE,
            SCOPE_CONSOLE,
            SCOPE_PROJECT_EXPLORER,
            SCOPE_PROBLEMS,
            SCOPE_PALETTE_MODE,
            SCOPE_CAPTURE_MODE,
            SCOPE_TILE_PAINT,
            SCOPE_ENTITY_PAINT,
            SCOPE_ENTITY_SELECT,
            SCOPE_AUTHORING_SELECTED,
            SCOPE_GLOBAL,
        ]
        assert len(scopes) == len(set(scopes)), "Scope constants have duplicate values"

    def test_scope_priority_is_tuple(self) -> None:
        """SCOPE_PRIORITY should be a tuple of scope strings."""
        assert isinstance(SCOPE_PRIORITY, tuple)
        for scope in SCOPE_PRIORITY:
            assert isinstance(scope, str)


class TestCaptureFocusSnapshot:
    """Test CaptureFocusSnapshot dataclass."""

    def test_snapshot_with_all_defaults(self) -> None:
        """Snapshot can be created via helper with all False."""
        snap = _make_snapshot()
        assert snap.is_confirm_modal_open is False
        assert snap.is_context_menu_open is False
        assert snap.show_debug is False

    def test_snapshot_with_overrides(self) -> None:
        """Snapshot fields can be overridden at construction."""
        snap = _make_snapshot(
            is_confirm_modal_open=True,
            show_debug=True,
        )
        assert snap.is_confirm_modal_open is True
        assert snap.show_debug is True

    def test_snapshot_is_frozen(self) -> None:
        """Snapshot should be immutable (frozen dataclass)."""
        snap = _make_snapshot()
        with pytest.raises(AttributeError):
            as_any(snap).show_debug = True


class TestComputeActiveScopes:
    """Test compute_active_scopes function."""

    def test_empty_snapshot_returns_global_only(self) -> None:
        """Empty snapshot (all False) returns only global scope."""
        snap = _make_snapshot()
        scopes = compute_active_scopes(snap)
        assert scopes == [SCOPE_GLOBAL]

    def test_confirm_modal_is_highest_priority(self) -> None:
        """confirm_modal scope should be first when active."""
        snap = _make_snapshot(
            is_confirm_modal_open=True,
            is_context_menu_open=True,
            is_command_palette_open=True,
            show_debug=True,
        )
        scopes = compute_active_scopes(snap)
        assert scopes[0] == SCOPE_CONFIRM_MODAL

    def test_context_menu_before_command_palette(self) -> None:
        """context_menu scope should come before command_palette."""
        snap = _make_snapshot(
            is_context_menu_open=True,
            is_command_palette_open=True,
            show_debug=True,
        )
        scopes = compute_active_scopes(snap)
        ctx_idx = scopes.index(SCOPE_CONTEXT_MENU)
        pal_idx = scopes.index(SCOPE_COMMAND_PALETTE)
        assert ctx_idx < pal_idx

    def test_console_included_when_active(self) -> None:
        """Console scope included when is_console_active is True."""
        snap = _make_snapshot(is_console_active=True)
        scopes = compute_active_scopes(snap)
        assert SCOPE_CONSOLE in scopes

    def test_tile_paint_before_entity_select(self) -> None:
        """tile_paint should have priority over entity_select."""
        snap = _make_snapshot(
            is_tile_paint_enabled=True,
            is_entity_select_active=True,
            show_debug=True,
        )
        scopes = compute_active_scopes(snap)
        if SCOPE_TILE_PAINT in scopes and SCOPE_ENTITY_SELECT in scopes:
            tile_idx = scopes.index(SCOPE_TILE_PAINT)
            select_idx = scopes.index(SCOPE_ENTITY_SELECT)
            assert tile_idx < select_idx

    def test_global_always_last(self) -> None:
        """Global scope should always be last in the list."""
        snap = _make_snapshot(
            is_confirm_modal_open=True,
            is_console_active=True,
            show_debug=True,
        )
        scopes = compute_active_scopes(snap)
        assert scopes[-1] == SCOPE_GLOBAL

    def test_deterministic_ordering(self) -> None:
        """Same snapshot should always produce same scope order."""
        snap = _make_snapshot(
            is_confirm_modal_open=True,
            is_context_menu_open=True,
            is_command_palette_open=True,
            is_console_active=True,
            show_debug=True,
        )
        first = compute_active_scopes(snap)
        second = compute_active_scopes(snap)
        assert first == second


class TestScopePriorityOrder:
    """Test the documented priority order of scopes."""

    EXPECTED_PRIORITY_ORDER = [
        SCOPE_CONFIRM_MODAL,
        SCOPE_CONTEXT_MENU,
        SCOPE_KEYBINDS,
        SCOPE_INLINE_RENAME,
        SCOPE_COMMAND_PALETTE,
        SCOPE_CONSOLE,
        SCOPE_PROJECT_EXPLORER,
        SCOPE_PROBLEMS,
        SCOPE_PALETTE_MODE,
        SCOPE_CAPTURE_MODE,
        SCOPE_TILE_PAINT,
        SCOPE_ENTITY_PAINT,
        SCOPE_ENTITY_SELECT,
        SCOPE_AUTHORING_SELECTED,
        SCOPE_GLOBAL,
    ]

    def test_all_scopes_in_priority(self) -> None:
        """Every scope constant should be in SCOPE_PRIORITY."""
        for expected in self.EXPECTED_PRIORITY_ORDER:
            assert expected in SCOPE_PRIORITY, f"Missing scope in priority: {expected}"

    def test_priority_order_matches(self) -> None:
        """SCOPE_PRIORITY constant should match expected order."""
        assert list(SCOPE_PRIORITY) == self.EXPECTED_PRIORITY_ORDER
