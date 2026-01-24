"""Integration tests for undo history controller wiring."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from engine import optional_arcade
from engine.editor_controller import EditorModeController


@dataclass
class StubWindow:
    width: int = 1280
    height: int = 720


class StubController:
    def __init__(self, undo_stack, redo_stack) -> None:
        self.active = True
        self._right_dock_tab = "History"
        self._history_cursor_index = 0
        self._history_search = ""
        self._search_focus = None
        self.undo_stack = list(undo_stack)
        self.redo_stack = list(redo_stack)
        self.undo_calls = 0
        self.redo_calls = 0
        self.window = StubWindow()
        self._dock_left_w = 320
        self._dock_right_w = 320
        self.palette_filter_active = False
        self.hierarchy_filter_active = False
        self.hierarchy_rename_active = False
        self.animation_edit_active = False
        self.inspector_edit_active = False
        self.command_palette_active = False
        self.entity_panels_filter_active = False
        self.scene_browser_filter_active = False
        self.asset_browser_filter_active = False
        self._unsaved_changes_pending = False
        self.scene_browser_active = False
        self.confirm_open = False

    def get_effective_dock_widths(self, window_w: int):
        return (self._dock_left_w, self._dock_right_w)

    def get_undo_history_entries(self):
        return EditorModeController.get_undo_history_entries(self)

    def get_filtered_undo_history_entries(self):
        return EditorModeController.get_filtered_undo_history_entries(self)

    def _clamp_history_cursor(self, cursor: int, count: int) -> int:
        return EditorModeController._clamp_history_cursor(self, cursor, count)

    def _history_current_index(self, entries):
        return EditorModeController._history_current_index(self, entries)

    def _history_display_index(self, entries):
        return EditorModeController._history_display_index(self, entries)

    def _history_input_blocked(self) -> bool:
        return EditorModeController._history_input_blocked(self)

    def _jump_by_delta(self, delta: int) -> None:
        return EditorModeController._jump_by_delta(self, delta)

    def undo_last(self) -> None:
        if not self.undo_stack:
            return
        cmd = self.undo_stack.pop()
        self.redo_stack.append(cmd)
        self.undo_calls += 1

    def redo_last(self) -> None:
        if not self.redo_stack:
            return
        cmd = self.redo_stack.pop()
        self.undo_stack.append(cmd)
        self.redo_calls += 1


def test_jump_calls_redo(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = StubController(
        undo_stack=[{"type": "MoveEntity"}, {"type": "RotateEntities"}],
        redo_stack=[{"type": "EditLight"}],
    )
    result = EditorModeController.jump_undo_history_to(ctrl, 0)
    assert result is True
    assert ctrl.redo_calls == 1
    assert ctrl.undo_calls == 0


def test_jump_calls_undo(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = StubController(
        undo_stack=[{"type": "MoveEntity"}, {"type": "RotateEntities"}],
        redo_stack=[{"type": "EditLight"}],
    )
    result = EditorModeController.jump_undo_history_to(ctrl, 2)
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

    ctrl.jump_undo_history_to = _jump
    ctrl.get_undo_history_entries = lambda: EditorModeController.get_undo_history_entries(ctrl)
    ctrl._clamp_history_cursor = lambda cursor, count: EditorModeController._clamp_history_cursor(ctrl, cursor, count)
    ctrl._history_input_blocked = lambda: False

    layout = compute_editor_shell_layout(ctrl.window.width, ctrl.window.height, 320, 320)
    dock = layout.right_dock
    content_top = dock.top - TAB_HEADER_HEIGHT - HISTORY_PADDING - HISTORY_LINE_HEIGHT

    x = dock.left + HISTORY_PADDING + 4
    y = content_top - HISTORY_LINE_HEIGHT / 2

    handled = EditorModeController._history_handle_mouse_click(
        ctrl, x, y, arcade_stub.MOUSE_BUTTON_LEFT
    )
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
    prev_cursor = ctrl._history_cursor_index

    handled = EditorModeController._handle_history_input(ctrl, arcade_stub.key.DOWN, 0)
    assert handled is True
    assert ctrl._history_cursor_index == prev_cursor
