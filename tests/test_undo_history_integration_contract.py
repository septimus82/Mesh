"""Integration tests for undo history controller wiring."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from engine import optional_arcade
from engine.editor.editor_history_controller import EditorHistoryController
from tests._dock_stub import make_dock_stub
from tests._search_stub import attach_search_stub
from tests._session_stub import make_session_stub


@dataclass
class StubWindow:
    width: int = 1280
    height: int = 720


class StubController:
    def __init__(self, undo_stack, redo_stack) -> None:
        self.active = True
        self.dock = make_dock_stub(right_tab="History")
        self.search = attach_search_stub(self)
        self.undo_calls = 0
        self.redo_calls = 0
        self.window = StubWindow()
        self.palette_filter_active = False
        self.hierarchy_filter_active = False
        self.hierarchy_rename_active = False
        self.animation_edit_active = False
        self.inspector_edit_active = False
        self.command_palette_active = False
        self.entity_panels_filter_active = False
        self.session = make_session_stub()
        self.scene_browser_filter_active = False
        self.asset_browser_filter_active = False
        self._unsaved_changes_pending = False
        self.scene_browser_active = False
        from types import SimpleNamespace
        self.unsaved_confirm = SimpleNamespace(is_open=False)
        from engine.editor.editor_undo_controller import EditorUndoController

        self.undo = EditorUndoController(self)
        self.undo.set_undo_stack(list(undo_stack))
        self.undo.set_redo_stack(list(redo_stack))
        self.history = EditorHistoryController(self)

    def get_effective_dock_widths(self, window_w: int):
        return self.dock.get_effective_dock_widths(window_w)

    def undo_last(self) -> None:
        if not self.undo.undo():
            return
        self.undo_calls += 1

    def redo_last(self) -> None:
        if not self.undo.redo():
            return
        self.redo_calls += 1


def test_jump_calls_redo(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = StubController(
        undo_stack=[{"type": "MoveEntity"}, {"type": "RotateEntities"}],
        redo_stack=[{"type": "EditLight"}],
    )
    result = ctrl.history.jump_to(0)
    assert result is True
    assert ctrl.redo_calls == 1
    assert ctrl.undo_calls == 0


def test_jump_calls_undo(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = StubController(
        undo_stack=[{"type": "MoveEntity"}, {"type": "RotateEntities"}],
        redo_stack=[{"type": "EditLight"}],
    )
    result = ctrl.history.jump_to(2)
    assert result is True
    assert ctrl.undo_calls == 1
    assert ctrl.redo_calls == 0


def test_mouse_click_triggers_jump(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import arcade_fallback as arcade_stub
    from engine.editor.editor_shell_layout import compute_editor_shell_layout, TAB_HEADER_HEIGHT
    from engine.editor.undo_history_model import HISTORY_LINE_HEIGHT, HISTORY_PADDING

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)

    ctrl = StubController(
        undo_stack=[{"type": "MoveEntity"}, {"type": "RotateEntities"}],
        redo_stack=[{"type": "EditLight"}],
    )

    called = {}

    def _jump(cursor_index: int) -> bool:
        called["cursor"] = cursor_index
        return True

    ctrl.history.jump_to = _jump  # type: ignore[assignment]

    layout = compute_editor_shell_layout(ctrl.window.width, ctrl.window.height, 320, 320)
    dock = layout.right_dock
    content_top = dock.top - TAB_HEADER_HEIGHT - HISTORY_PADDING - HISTORY_LINE_HEIGHT

    x = dock.left + HISTORY_PADDING + 4
    y = content_top - HISTORY_LINE_HEIGHT / 2

    handled = ctrl.history.handle_mouse_click(x, y, arcade_stub.MOUSE_BUTTON_LEFT)
    assert handled is True
    assert called.get("cursor") == 0


def test_history_input_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)

    ctrl = StubController(
        undo_stack=[{"type": "MoveEntity"}],
        redo_stack=[],
    )
    ctrl.palette_filter_active = True
    prev_cursor = ctrl.history.get_cursor_index()

    handled = ctrl.history.handle_input(arcade_stub.key.DOWN, 0)
    assert handled is True
    assert ctrl.history.get_cursor_index() == prev_cursor
