from __future__ import annotations

from typing import Any
from types import SimpleNamespace

import engine.optional_arcade as optional_arcade
from engine.editor.shortcut_resolver_model import (
    SHORTCUT_SCOPE_GLOBAL,
    SHORTCUT_SCOPE_PROJECT_EXPLORER_CONTEXT_MENU,
)
from engine.editor_runtime.editor_input_router import route_and_dispatch
from tests._session_stub import make_session_stub


class _DummyController:
    def __init__(self) -> None:
        self.window = None
        self._palette_open = False
        self.search = self._SearchState()
        self._run_calls: list[str] = []
        self.keybinds = None
        self.panels = self._DummyPanels(self)
        self.session = make_session_stub()

    class _SearchState:
        def __init__(self) -> None:
            self._query = ""
            self._index = 0

        @property
        def command_palette_query(self) -> str:
            return self._query

        @command_palette_query.setter
        def command_palette_query(self, value: str) -> None:
            self._query = str(value or "")

        @property
        def command_palette_index(self) -> int:
            return self._index

        @command_palette_index.setter
        def command_palette_index(self, value: int) -> None:
            self._index = int(value or 0)

        def clear_command_palette_state(self) -> None:
            self._query = ""
            self._index = 0

        def get_command_palette_state(self) -> tuple[str, int]:
            return (self._query, int(self._index))

        def backspace_command_palette(self) -> bool:
            if not self._query:
                return False
            self._query = self._query[:-1]
            self._index = 0
            return True

        def move_command_palette_selection(self, delta: int) -> None:
            self._index = max(0, int(self._index) + int(delta))

    def run_editor_action(self, action_id: str) -> bool:
        self._run_calls.append(action_id)
        return True

    class _DummyPanels:
        def __init__(self, controller: "_DummyController") -> None:
            self._controller = controller

        def is_command_palette_open(self) -> bool:
            return bool(self._controller._palette_open)

        def close_command_palette(self) -> None:
            self._controller._palette_open = False


def test_command_palette_escape_closes() -> None:
    ctl = _DummyController()
    ctl._palette_open = True
    ctl.search.command_palette_query = "abc"
    ctl.search.command_palette_index = 3
    snapshot = {
        "focus_target": "command_palette",
        "text_input_active": True,
        "scopes": (SHORTCUT_SCOPE_GLOBAL,),
    }
    handled = route_and_dispatch(ctl, optional_arcade.arcade.key.ESCAPE, 0, snapshot)
    assert handled is True
    assert ctl._palette_open is False
    assert ctl.search.command_palette_query == ""
    assert ctl.search.command_palette_index == 0


def test_global_undo_blocked_by_text_input() -> None:
    ctl = _DummyController()
    snapshot = {
        "focus_target": "command_palette",
        "text_input_active": True,
        "scopes": (SHORTCUT_SCOPE_GLOBAL,),
    }
    handled = route_and_dispatch(
        ctl,
        optional_arcade.arcade.key.Z,
        optional_arcade.arcade.key.MOD_CTRL,
        snapshot,
    )
    assert handled is False
    assert ctl._run_calls == []


def test_project_explorer_context_menu_down_dispatches_action() -> None:
    ctl = _DummyController()
    snapshot = {
        "focus_target": "project_explorer_context_menu",
        "text_input_active": False,
        "scopes": (SHORTCUT_SCOPE_PROJECT_EXPLORER_CONTEXT_MENU,),
    }
    handled = route_and_dispatch(ctl, optional_arcade.arcade.key.DOWN, 0, snapshot)
    assert handled is True
    assert ctl._run_calls == ["editor.project_explorer.context_menu.down"]
