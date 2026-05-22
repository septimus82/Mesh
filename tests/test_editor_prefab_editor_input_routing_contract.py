from __future__ import annotations

from types import SimpleNamespace

import pytest

import engine.optional_arcade as optional_arcade
from engine.editor_runtime import (
    editor_input_click_handlers,
    editor_input_key_handlers,
    editor_input_text_handlers,
)
from tests._dock_stub import make_dock_stub

pytestmark = [pytest.mark.fast]


class _PrefabEditorStub:
    def __init__(self, *, active: bool = True) -> None:
        self._active = active
        self.calls: list[tuple[str, object]] = []

    def is_edit_mode_active(self) -> bool:
        return self._active

    def handle_prefab_editor_text_input(self, text: str) -> bool:
        self.calls.append(("text", text))
        return True

    def handle_prefab_editor_key(self, key: int, modifiers: int) -> bool:
        self.calls.append(("key", (key, modifiers)))
        return True

    def cycle_focus_forward(self) -> None:
        self.calls.append(("cycle", "forward"))

    def cycle_focus_backward(self) -> None:
        self.calls.append(("cycle", "backward"))

    def handle_prefab_editor_mouse_click(self, x: float, y: float) -> bool:
        self.calls.append(("click", (x, y)))
        return True


def _controller(*, right_tab: str = "Prefabs", edit_mode: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        active=True,
        dock=make_dock_stub(right_tab=right_tab),
        prefab_editor=_PrefabEditorStub(active=edit_mode),
        item_editor=None,
        panels=SimpleNamespace(dispatch_input=lambda _key, _mods: False),
        search=None,
        _find_everything_open=False,
        asset_place_active=False,
        asset_browser_active=False,
        window=SimpleNamespace(width=1280, height=720),
    )


def test_prefab_editor_text_input_routes_only_when_prefabs_tab_and_edit_mode() -> None:
    controller = _controller()

    editor_input_text_handlers.handle_text_input(controller, "x")

    assert controller.prefab_editor.calls == [("text", "x")]
    wrong_tab = _controller(right_tab="Items")
    assert editor_input_text_handlers._prefab_editor_should_route(wrong_tab, wrong_tab.prefab_editor) is False
    inactive = _controller(edit_mode=False)
    assert editor_input_text_handlers._prefab_editor_should_route(inactive, inactive.prefab_editor) is False


def test_prefab_editor_key_routes_only_when_prefabs_tab_and_edit_mode() -> None:
    controller = _controller()

    handled = editor_input_key_handlers.handle_pre_routed_keys(controller, optional_arcade.arcade.key.BACKSPACE, 0)

    assert handled is True
    assert controller.prefab_editor.calls == [("key", (optional_arcade.arcade.key.BACKSPACE, 0))]
    wrong_tab = _controller(right_tab="History")
    assert editor_input_key_handlers._prefab_editor_should_route(wrong_tab, wrong_tab.prefab_editor) is False
    inactive = _controller(edit_mode=False)
    assert editor_input_key_handlers._prefab_editor_should_route(inactive, inactive.prefab_editor) is False


def test_prefab_editor_tab_cycles_focus_when_prefabs_tab_and_edit_mode() -> None:
    controller = _controller()

    handled = editor_input_key_handlers.handle_pre_routed_keys(controller, optional_arcade.arcade.key.TAB, 0)
    shifted = editor_input_key_handlers.handle_pre_routed_keys(
        controller,
        optional_arcade.arcade.key.TAB,
        optional_arcade.arcade.key.MOD_SHIFT,
    )

    assert handled is True
    assert shifted is True
    assert controller.prefab_editor.calls == [("cycle", "forward"), ("cycle", "backward")]


def test_prefab_editor_click_routes_only_when_prefabs_tab_and_edit_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = _controller()
    monkeypatch.setattr(editor_input_click_handlers, "_handle_menu_bar_click", lambda *_args: None)
    monkeypatch.setattr(editor_input_click_handlers, "_handle_top_bar_controls_click", lambda *_args: None)
    monkeypatch.setattr(editor_input_click_handlers, "_handle_splitter_click", lambda *_args: None)
    monkeypatch.setattr(editor_input_click_handlers, "_handle_dock_tab_click", lambda *_args: None)

    handled = editor_input_click_handlers.handle_mouse_click(
        controller,
        12.0,
        34.0,
        optional_arcade.arcade.MOUSE_BUTTON_LEFT,
        0,
    )

    assert handled is True
    assert controller.prefab_editor.calls == [("click", (12.0, 34.0))]
    wrong_tab = _controller(right_tab="Problems")
    assert editor_input_click_handlers._prefab_editor_should_route(wrong_tab, wrong_tab.prefab_editor) is False
    inactive = _controller(edit_mode=False)
    assert editor_input_click_handlers._prefab_editor_should_route(inactive, inactive.prefab_editor) is False
