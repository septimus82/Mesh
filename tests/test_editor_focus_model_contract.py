"""Contract tests for editor_focus_model."""
from __future__ import annotations

from types import SimpleNamespace

from engine.editor.editor_focus_model import (
    FOCUS_COMMAND_PALETTE,
    FOCUS_INLINE_RENAME,
    FOCUS_PALETTE,
    FOCUS_PROJECT_EXPLORER,
    compute_active_shortcut_scopes,
    derive_focus_target,
    is_text_input_active,
)
from engine.editor.shortcut_resolver_model import (
    SHORTCUT_SCOPE_GLOBAL,
    SHORTCUT_SCOPE_INLINE_RENAME,
)


def test_focus_determinism() -> None:
    state = {"command_palette_active": True}
    assert derive_focus_target(state) == FOCUS_COMMAND_PALETTE
    assert derive_focus_target(state) == FOCUS_COMMAND_PALETTE


def test_inline_rename_scopes_override() -> None:
    state = {
        "project_explorer": SimpleNamespace(inline_rename_active=True),
    }
    focus_target = derive_focus_target(state)
    assert focus_target == FOCUS_INLINE_RENAME
    scopes = compute_active_shortcut_scopes(focus_target, state)
    assert scopes == (SHORTCUT_SCOPE_INLINE_RENAME, SHORTCUT_SCOPE_GLOBAL)


def test_palette_text_input_blocks() -> None:
    state = {"palette_filter_active": True}
    focus_target = derive_focus_target(state)
    assert focus_target == FOCUS_PALETTE
    assert is_text_input_active(focus_target, state) is True


def test_project_explorer_focus_from_left_tab() -> None:
    state = {"_left_dock_tab": "Project"}
    assert derive_focus_target(state) == FOCUS_PROJECT_EXPLORER