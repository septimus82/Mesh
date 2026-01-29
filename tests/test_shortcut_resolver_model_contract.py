"""Contract tests for shortcut resolver model."""

from __future__ import annotations

from dataclasses import dataclass, field

import engine.optional_arcade as optional_arcade

from engine.editor.editor_actions import get_editor_actions
from engine.editor.shortcut_resolver_model import (
    build_shortcut_map,
    build_shortcut_map_by_scope,
    normalize_shortcut_event,
    normalize_shortcut_text,
    resolve_shortcut,
    resolve_shortcut_scoped,
    validate_shortcut_scopes,
    SHORTCUT_SCOPE_GLOBAL,
    SHORTCUT_SCOPE_INLINE_RENAME,
)


@dataclass(frozen=True)
class _Action:
    id: str
    shortcut: str
    shortcut_scope: str = SHORTCUT_SCOPE_GLOBAL


def test_shortcut_normalization_stable() -> None:
    assert normalize_shortcut_text("alt+ctrl+b") == "Ctrl+Alt+B"
    key = optional_arcade.arcade.key.B
    modifiers = optional_arcade.arcade.key.MOD_CTRL | optional_arcade.arcade.key.MOD_ALT
    assert normalize_shortcut_event(key, modifiers) == "Ctrl+Alt+B"


def test_shortcut_resolution_deterministic_on_conflict() -> None:
    actions = [_Action("a.action", "Ctrl+S"), _Action("b.action", "Ctrl+S")]
    shortcut_map = build_shortcut_map(actions)
    assert resolve_shortcut(shortcut_map, "ctrl+s") == "a.action"


def test_no_duplicate_shortcuts_within_same_scope() -> None:
    """Verify no duplicate shortcuts exist within the same scope in the registry."""
    actions = get_editor_actions(None, None)
    errors = validate_shortcut_scopes(actions)
    assert errors == [], f"Duplicate shortcuts found: {errors}"


# --- Scoped Resolution Tests ---


def test_scoped_resolution_prefers_active_scope() -> None:
    """When scope is active, scoped shortcut takes priority over global."""
    actions = [
        _Action("global.enter", "Enter", SHORTCUT_SCOPE_GLOBAL),
        _Action("rename.enter", "Enter", SHORTCUT_SCOPE_INLINE_RENAME),
    ]
    scope_maps = build_shortcut_map_by_scope(actions)
    
    # With inline rename scope active, scoped action wins
    active_scopes = [SHORTCUT_SCOPE_INLINE_RENAME, SHORTCUT_SCOPE_GLOBAL]
    assert resolve_shortcut_scoped(scope_maps, "Enter", active_scopes) == "rename.enter"
    
    # With only global scope, global action is used
    active_scopes = [SHORTCUT_SCOPE_GLOBAL]
    assert resolve_shortcut_scoped(scope_maps, "Enter", active_scopes) == "global.enter"


def test_scoped_resolution_falls_back_to_global() -> None:
    """If no scoped match, falls back to global scope."""
    actions = [
        _Action("global.save", "Ctrl+S", SHORTCUT_SCOPE_GLOBAL),
        _Action("rename.enter", "Enter", SHORTCUT_SCOPE_INLINE_RENAME),
    ]
    scope_maps = build_shortcut_map_by_scope(actions)
    
    # Ctrl+S only exists in global, so it resolves there even with inline_rename active
    active_scopes = [SHORTCUT_SCOPE_INLINE_RENAME, SHORTCUT_SCOPE_GLOBAL]
    assert resolve_shortcut_scoped(scope_maps, "Ctrl+S", active_scopes) == "global.save"


def test_scoped_resolution_returns_none_for_no_match() -> None:
    """Returns None when no matching shortcut in any active scope."""
    actions = [
        _Action("global.save", "Ctrl+S", SHORTCUT_SCOPE_GLOBAL),
    ]
    scope_maps = build_shortcut_map_by_scope(actions)
    
    active_scopes = [SHORTCUT_SCOPE_GLOBAL]
    assert resolve_shortcut_scoped(scope_maps, "Ctrl+Q", active_scopes) is None


def test_validate_shortcut_scopes_detects_duplicates() -> None:
    """validate_shortcut_scopes detects duplicates within same scope."""
    actions = [
        _Action("a.action", "Ctrl+S", SHORTCUT_SCOPE_GLOBAL),
        _Action("b.action", "Ctrl+S", SHORTCUT_SCOPE_GLOBAL),  # Duplicate in global
    ]
    errors = validate_shortcut_scopes(actions)
    assert len(errors) == 1
    assert "Ctrl+S" in errors[0]
    assert "global" in errors[0]


def test_validate_shortcut_scopes_allows_cross_scope_duplicates() -> None:
    """Same shortcut in different scopes is allowed."""
    actions = [
        _Action("global.enter", "Enter", SHORTCUT_SCOPE_GLOBAL),
        _Action("rename.enter", "Enter", SHORTCUT_SCOPE_INLINE_RENAME),
    ]
    errors = validate_shortcut_scopes(actions)
    assert errors == []


def test_build_shortcut_map_by_scope_deterministic() -> None:
    """First action wins for deterministic resolution within a scope."""
    actions = [
        _Action("first.action", "Ctrl+S", SHORTCUT_SCOPE_GLOBAL),
        _Action("second.action", "Ctrl+S", SHORTCUT_SCOPE_GLOBAL),
    ]
    scope_maps = build_shortcut_map_by_scope(actions)
    
    # First action should win
    assert scope_maps[SHORTCUT_SCOPE_GLOBAL]["Ctrl+S"] == "first.action"


def test_inline_rename_actions_have_correct_scope() -> None:
    """Verify inline rename actions are scoped to text_input.inline_rename."""
    actions = get_editor_actions(None, None)
    
    inline_rename_ids = [
        "editor.project_explorer.inline_rename.commit",
        "editor.project_explorer.inline_rename.cancel",
        "editor.project_explorer.inline_rename.backspace",
        "editor.project_explorer.inline_rename.delete",
    ]
    
    for action in actions:
        if action.id in inline_rename_ids:
            assert action.shortcut_scope == SHORTCUT_SCOPE_INLINE_RENAME, (
                f"Action {action.id} should have scope {SHORTCUT_SCOPE_INLINE_RENAME}"
            )
