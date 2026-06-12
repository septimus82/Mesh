"""Contract tests for editor_focus_model."""
from __future__ import annotations

from types import SimpleNamespace

from engine.editor.editor_focus_model import (
    FOCUS_COMMAND_PALETTE,
    FOCUS_INLINE_RENAME,
    FOCUS_PALETTE,
    FOCUS_PROJECT_EXPLORER,
    FOCUS_PROJECT_EXPLORER_CONTEXT_MENU,
    compute_active_shortcut_scopes,
    derive_focus_target,
    is_text_input_active,
)
from engine.editor.shortcut_resolver_model import (
    SHORTCUT_SCOPE_GLOBAL,
    SHORTCUT_SCOPE_INLINE_RENAME,
    SHORTCUT_SCOPE_PROJECT_EXPLORER,
    SHORTCUT_SCOPE_PROJECT_EXPLORER_CONTEXT_MENU,
)
from tests._dock_stub import make_dock_stub
from tests._session_stub import make_session_stub


def test_focus_determinism() -> None:
    panels = SimpleNamespace(is_command_palette_open=lambda: True)
    state = {"panels": panels}
    snapshot = make_session_stub().get_snapshot()
    assert derive_focus_target(state, snapshot) == FOCUS_COMMAND_PALETTE
    assert derive_focus_target(state, snapshot) == FOCUS_COMMAND_PALETTE


def test_inline_rename_scopes_override() -> None:
    state = {
        "project_explorer": SimpleNamespace(inline_rename_active=True),
    }
    focus_target = derive_focus_target(state, make_session_stub().get_snapshot())
    assert focus_target == FOCUS_INLINE_RENAME
    scopes = compute_active_shortcut_scopes(focus_target, state)
    assert scopes == (SHORTCUT_SCOPE_INLINE_RENAME, SHORTCUT_SCOPE_GLOBAL)


def test_palette_text_input_blocks() -> None:
    state = {"palette_filter_active": True}
    focus_target = derive_focus_target(state, make_session_stub().get_snapshot())
    assert focus_target == FOCUS_PALETTE
    assert is_text_input_active(focus_target, state) is True


def test_project_explorer_focus_from_left_tab() -> None:
    state = {"dock": make_dock_stub(left_tab="Project")}
    assert derive_focus_target(state, make_session_stub().get_snapshot()) == FOCUS_PROJECT_EXPLORER


def test_project_explorer_scopes() -> None:
    state = {"dock": make_dock_stub(left_tab="Project")}
    focus_target = derive_focus_target(state, make_session_stub().get_snapshot())
    scopes = compute_active_shortcut_scopes(focus_target, state)
    assert scopes == (SHORTCUT_SCOPE_PROJECT_EXPLORER, SHORTCUT_SCOPE_GLOBAL)


def test_context_menu_focus_overrides_inline_rename() -> None:
    state = {
        "panels": SimpleNamespace(is_project_context_menu_open=lambda: True),
        "project_explorer": SimpleNamespace(
            inline_rename_active=True,
        ),
    }
    focus_target = derive_focus_target(state, make_session_stub().get_snapshot())
    assert focus_target == FOCUS_PROJECT_EXPLORER_CONTEXT_MENU
    scopes = compute_active_shortcut_scopes(focus_target, state)
    assert scopes == (SHORTCUT_SCOPE_PROJECT_EXPLORER_CONTEXT_MENU,)
