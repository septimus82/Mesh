"""Contract tests for shortcut dispatch in editor input."""

from __future__ import annotations

from types import SimpleNamespace

import engine.optional_arcade as optional_arcade

from engine.editor_runtime import input as editor_input
from engine.editor_runtime import editor_input_shortcut_handlers as editor_shortcuts
from engine.editor.editor_project_explorer_actions_controller import (
    EditorProjectExplorerActionsController,
)
from tests._session_stub import make_session_stub
from tests._dock_stub import make_dock_stub


def _stub_controller() -> SimpleNamespace:
    search_stub = SimpleNamespace(
        get_search_focus=lambda: "",
        is_search_focused=lambda: False,
        focus_search_for_active_panel=lambda: False,
    )
    return SimpleNamespace(
        active=True,
        palette_filter_active=False,
        hierarchy_filter_active=False,
        hierarchy_rename_active=False,
        animation_edit_active=False,
        inspector_edit_active=False,
        entity_panels_filter_active=False,
        entity_panels_active=False,
        tool_mode="",
        search=search_stub,
        project_explorer=SimpleNamespace(inline_rename_active=False),
        panels=SimpleNamespace(
            is_command_palette_open=lambda: False,
            dispatch_input=lambda key, modifiers: False,
        ),
        window=SimpleNamespace(),
        session=make_session_stub(),
        dock=make_dock_stub(),
    )


def test_shortcut_executes_action_when_enabled(monkeypatch) -> None:
    controller = _stub_controller()
    calls: list[str] = []

    def fake_get_actions(_controller, _window):
        return [SimpleNamespace(
            id="test.action",
            shortcut="Ctrl+Alt+B",
            shortcut_scope="global",
            enabled=lambda c, w: True,
        )]

    def fake_run(action_id, _controller, _window):
        calls.append(action_id)
        return True

    monkeypatch.setattr(editor_shortcuts, "get_editor_actions", fake_get_actions)
    monkeypatch.setattr(editor_shortcuts, "run_editor_action", fake_run)

    key = optional_arcade.arcade.key.B
    modifiers = optional_arcade.arcade.key.MOD_CTRL | optional_arcade.arcade.key.MOD_ALT
    assert editor_input._handle_editor_action_shortcut(controller, key, modifiers) is True
    assert calls == ["test.action"]


def test_shortcut_ignored_while_text_input_active_and_disabled(monkeypatch) -> None:
    """Shortcuts don't run when text input is active AND action is disabled."""
    controller = _stub_controller()
    controller.panels = SimpleNamespace(is_command_palette_open=lambda: True)
    calls: list[str] = []

    def fake_get_actions(_controller, _window):
        # Action with enablement that returns False during text input
        return [SimpleNamespace(
            id="test.action",
            shortcut="Ctrl+Alt+B",
            shortcut_scope="global",
            enabled=lambda c, w: False,  # Disabled
        )]

    def fake_run(action_id, _controller, _window):
        calls.append(action_id)
        return True

    monkeypatch.setattr(editor_shortcuts, "get_editor_actions", fake_get_actions)
    monkeypatch.setattr(editor_shortcuts, "run_editor_action", fake_run)

    key = optional_arcade.arcade.key.B
    modifiers = optional_arcade.arcade.key.MOD_CTRL | optional_arcade.arcade.key.MOD_ALT
    # Returns False because action is disabled
    assert editor_input._handle_editor_action_shortcut(controller, key, modifiers) is False
    assert calls == []


def test_shortcut_runs_when_text_input_active_and_enabled(monkeypatch) -> None:
    """Shortcuts CAN run when text input is active IF action is enabled."""
    controller = _stub_controller()
    controller.panels = SimpleNamespace(is_command_palette_open=lambda: True)
    calls: list[str] = []

    def fake_get_actions(_controller, _window):
        # Action that is enabled even during text input
        return [SimpleNamespace(
            id="test.text_input_action",
            shortcut="Ctrl+Alt+B",
            shortcut_scope="global",
            enabled=lambda c, w: True,  # Enabled
        )]

    def fake_run(action_id, _controller, _window):
        calls.append(action_id)
        return True

    monkeypatch.setattr(editor_shortcuts, "get_editor_actions", fake_get_actions)
    monkeypatch.setattr(editor_shortcuts, "run_editor_action", fake_run)

    key = optional_arcade.arcade.key.B
    modifiers = optional_arcade.arcade.key.MOD_CTRL | optional_arcade.arcade.key.MOD_ALT
    # Returns True because enabled action was found and executed
    assert editor_input._handle_editor_action_shortcut(controller, key, modifiers) is True
    assert calls == ["test.text_input_action"]


def test_handle_input_dispatches_shortcut_once(monkeypatch) -> None:
    controller = _stub_controller()
    calls: list[str] = []

    def fake_get_actions(_controller, _window):
        return [SimpleNamespace(
            id="editor.scene.save",
            shortcut="Ctrl+S",
            shortcut_scope="global",
            enabled=lambda c, w: True,
        )]

    def fake_run(action_id, _controller, _window):
        calls.append(action_id)
        return True

    monkeypatch.setattr(editor_shortcuts, "get_editor_actions", fake_get_actions)
    monkeypatch.setattr(editor_shortcuts, "run_editor_action", fake_run)

    key = optional_arcade.arcade.key.S
    modifiers = optional_arcade.arcade.key.MOD_CTRL
    assert editor_input.handle_input(controller, key, modifiers) is True
    assert calls == ["editor.scene.save"]


def test_handle_input_blocks_shortcut_during_text_input(monkeypatch) -> None:
    """Shortcuts are blocked during text input if action is disabled."""
    controller = _stub_controller()
    # When command palette is open, dispatch_input should consume Ctrl+S
    controller.panels = SimpleNamespace(
        is_command_palette_open=lambda: True,
        dispatch_input=lambda key, modifiers: True,  # Panels consume the input
    )
    calls: list[str] = []

    def fake_get_actions(_controller, _window):
        # Action with enablement that returns False during text input
        return [SimpleNamespace(
            id="editor.scene.save",
            shortcut="Ctrl+S",
            shortcut_scope="global",
            enabled=lambda c, w: False,  # Disabled during text input
        )]

    def fake_run(action_id, _controller, _window):
        calls.append(action_id)
        return True

    monkeypatch.setattr(editor_shortcuts, "get_editor_actions", fake_get_actions)
    monkeypatch.setattr(editor_shortcuts, "run_editor_action", fake_run)

    key = optional_arcade.arcade.key.S
    modifiers = optional_arcade.arcade.key.MOD_CTRL
    # Input consumed by panels (dispatch_input returns True)
    assert editor_input.handle_input(controller, key, modifiers) is True
    assert calls == []


def test_handle_input_ctrl_j_uses_registry(monkeypatch) -> None:
    controller = _stub_controller()
    calls: list[str] = []

    def fake_get_actions(_controller, _window):
        return [SimpleNamespace(
            id="editor.find_everything.toggle",
            shortcut="Ctrl+J",
            shortcut_scope="global",
            enabled=lambda c, w: True,
        )]

    def fake_run(action_id, _controller, _window):
        calls.append(action_id)
        return True

    monkeypatch.setattr(editor_shortcuts, "get_editor_actions", fake_get_actions)
    monkeypatch.setattr(editor_shortcuts, "run_editor_action", fake_run)

    key = optional_arcade.arcade.key.J
    modifiers = optional_arcade.arcade.key.MOD_CTRL
    assert editor_input.handle_input(controller, key, modifiers) is True
    assert calls == ["editor.find_everything.toggle"]


def test_handle_input_panel_toggle_shortcut(monkeypatch) -> None:
    controller = _stub_controller()
    calls: list[str] = []

    def fake_run(action_id, _controller, _window):
        calls.append(action_id)
        return True

    monkeypatch.setattr(editor_shortcuts, "run_editor_action", fake_run)

    key = optional_arcade.arcade.key.KEY_1
    modifiers = optional_arcade.arcade.key.MOD_CTRL | optional_arcade.arcade.key.MOD_ALT
    assert editor_input.handle_input(controller, key, modifiers) is True
    assert calls == ["editor.panel.inspector.toggle"]


# --- Inline Rename Action Dispatch Tests (via scoped shortcuts) ---


def _stub_controller_with_project_explorer(inline_rename_active: bool = False) -> SimpleNamespace:
    """Create controller stub with project explorer for inline rename tests."""
    project_ctrl = SimpleNamespace(
        inline_rename_active=inline_rename_active,
        selectable_rows=[],
        selected_index=0,
        ensure_rows=lambda: None,
        move_selection=lambda _delta, extend=False: None,
    )
    controller = SimpleNamespace(
        active=True,
        palette_filter_active=False,
        hierarchy_filter_active=False,
        hierarchy_rename_active=False,
        animation_edit_active=False,
        inspector_edit_active=False,
        entity_panels_filter_active=False,
        tool_mode="",
        search=SimpleNamespace(
            get_search_focus=lambda: "",
            is_search_focused=lambda: False,
            focus_search_for_active_panel=lambda: False,
        ),
        dock=make_dock_stub(left_tab="Project"),
        project_explorer=project_ctrl,
        panels=SimpleNamespace(is_command_palette_open=lambda: False),
        window=SimpleNamespace(),
        session=make_session_stub(),
    )
    controller.project_explorer_actions = EditorProjectExplorerActionsController(controller)
    return controller


def test_inline_rename_enter_dispatches_commit_action(monkeypatch) -> None:
    """Enter key during inline rename dispatches commit action via scoped shortcut."""
    controller = _stub_controller_with_project_explorer(inline_rename_active=True)
    calls: list[str] = []

    def fake_run(action_id, _controller, _window):
        calls.append(action_id)
        return True

    monkeypatch.setattr(editor_shortcuts, "run_editor_action", fake_run)

    # Enter key via scoped shortcut dispatch
    result = editor_input._handle_editor_action_shortcut(
        controller, optional_arcade.arcade.key.ENTER, 0
    )

    assert result is True
    assert "editor.project_explorer.inline_rename.commit" in calls


def test_inline_rename_escape_dispatches_cancel_action(monkeypatch) -> None:
    """Escape key during inline rename dispatches cancel action via scoped shortcut."""
    controller = _stub_controller_with_project_explorer(inline_rename_active=True)
    calls: list[str] = []

    def fake_run(action_id, _controller, _window):
        calls.append(action_id)
        return True

    monkeypatch.setattr(editor_shortcuts, "run_editor_action", fake_run)

    result = editor_input._handle_editor_action_shortcut(
        controller, optional_arcade.arcade.key.ESCAPE, 0
    )

    assert result is True
    assert "editor.project_explorer.inline_rename.cancel" in calls


def test_focus_snapshot_scopes_override_state(monkeypatch) -> None:
    """Focus snapshot scopes should drive shortcut resolution."""
    controller = _stub_controller_with_project_explorer(inline_rename_active=False)
    calls: list[str] = []

    controller.focus = SimpleNamespace(
        get_focus_snapshot=lambda: {
            "focus_target": "inline_rename",
            "text_input_active": True,
            "scopes": ("text_input.inline_rename", "global"),
        }
    )

    def fake_get_actions(_controller, _window):
        return [SimpleNamespace(
            id="editor.project_explorer.inline_rename.cancel",
            shortcut="Escape",
            shortcut_scope="text_input.inline_rename",
            enabled=lambda c, w: True,
        )]

    def fake_run(action_id, _controller, _window):
        calls.append(action_id)
        return True

    monkeypatch.setattr(editor_shortcuts, "get_editor_actions", fake_get_actions)
    monkeypatch.setattr(editor_shortcuts, "run_editor_action", fake_run)

    result = editor_input._handle_editor_action_shortcut(
        controller, optional_arcade.arcade.key.ESCAPE, 0
    )

    assert result is True
    assert calls == ["editor.project_explorer.inline_rename.cancel"]


def test_inline_rename_backspace_dispatches_backspace_action(monkeypatch) -> None:
    """Backspace key during inline rename dispatches backspace action via scoped shortcut."""
    controller = _stub_controller_with_project_explorer(inline_rename_active=True)
    calls: list[str] = []

    def fake_run(action_id, _controller, _window):
        calls.append(action_id)
        return True

    monkeypatch.setattr(editor_shortcuts, "run_editor_action", fake_run)

    result = editor_input._handle_editor_action_shortcut(
        controller, optional_arcade.arcade.key.BACKSPACE, 0
    )

    assert result is True
    assert "editor.project_explorer.inline_rename.backspace" in calls


def test_inline_rename_delete_dispatches_delete_action(monkeypatch) -> None:
    """Delete key during inline rename dispatches delete action via scoped shortcut."""
    controller = _stub_controller_with_project_explorer(inline_rename_active=True)
    calls: list[str] = []

    def fake_run(action_id, _controller, _window):
        calls.append(action_id)
        return True

    monkeypatch.setattr(editor_shortcuts, "run_editor_action", fake_run)

    result = editor_input._handle_editor_action_shortcut(
        controller, optional_arcade.arcade.key.DELETE, 0
    )

    assert result is True
    assert "editor.project_explorer.inline_rename.delete" in calls


def test_inline_rename_inactive_enter_uses_global(monkeypatch) -> None:
    """When inline rename not active, Enter uses global scope action if any."""
    controller = _stub_controller_with_project_explorer(inline_rename_active=False)
    calls: list[str] = []

    # Create mock actions with both global and scoped Enter
    def fake_get_actions(_controller, _window):
        return [
            SimpleNamespace(
                id="global.enter.action",
                shortcut="Enter",
                shortcut_scope="global",
                enabled=lambda c, w: True,
            ),
            SimpleNamespace(
                id="editor.project_explorer.inline_rename.commit",
                shortcut="Enter",
                shortcut_scope="text_input.inline_rename",
                enabled=lambda c, w: c.project_explorer.inline_rename_active,
            ),
        ]

    def fake_run(action_id, _controller, _window):
        calls.append(action_id)
        return True

    monkeypatch.setattr(editor_shortcuts, "get_editor_actions", fake_get_actions)
    monkeypatch.setattr(editor_shortcuts, "run_editor_action", fake_run)

    # When not in inline rename mode, Enter should resolve to global scope action
    result = editor_input._handle_editor_action_shortcut(
        controller, optional_arcade.arcade.key.ENTER, 0
    )

    # Should find global Enter action
    assert result is True
    assert "global.enter.action" in calls
    assert "editor.project_explorer.inline_rename.commit" not in calls


def test_inline_rename_consumes_other_keys() -> None:
    """Other keys during inline rename are consumed by _handle_project_explorer_input."""
    from engine import editor_controller as ec_module
    
    controller = _stub_controller_with_project_explorer(inline_rename_active=True)
    handler = ec_module.EditorModeController._handle_project_explorer_input
    
    # Regular letter key should be consumed but not dispatched as action
    result = handler(controller, optional_arcade.arcade.key.A, 0)
    assert result is True
