from __future__ import annotations

from types import SimpleNamespace

import pytest

import engine.optional_arcade as optional_arcade
from engine.editor_runtime import (
    editor_input_click_handlers,
    editor_input_key_handlers,
    editor_input_text_handlers,
)
from engine.editor_runtime.editor_database_form_input import dispatch_database_form_click
from tests._dock_stub import make_dock_stub

pytestmark = [pytest.mark.fast]


class _QuestEditorStub:
    def __init__(self, *, active: bool = True) -> None:
        self._active = active
        self.calls: list[tuple[str, object]] = []

    def is_edit_mode_active(self) -> bool:
        return self._active

    def handle_quest_editor_text_input(self, text: str) -> bool:
        self.calls.append(("text", text))
        return True

    def handle_quest_editor_key(self, key: int, modifiers: int) -> bool:
        self.calls.append(("key", (key, modifiers)))
        return True

    def cycle_focus_forward(self) -> None:
        self.calls.append(("cycle", "forward"))

    def cycle_focus_backward(self) -> None:
        self.calls.append(("cycle", "backward"))

    def handle_quest_editor_mouse_click(self, x: float, y: float) -> bool:
        self.calls.append(("click", (x, y)))
        return True


def _controller(
    *,
    right_tab: str = "Quests",
    edit_mode: bool = True,
    include_quest_editor: bool = True,
) -> SimpleNamespace:
    window = SimpleNamespace(
        width=1280,
        height=720,
        screen_to_world=lambda x, y: (x, y),
        scene_controller=SimpleNamespace(all_sprites=[]),
    )
    return SimpleNamespace(
        active=True,
        dock=make_dock_stub(right_tab=right_tab),
        quest_editor=_QuestEditorStub(active=edit_mode) if include_quest_editor else None,
        prefab_editor=None,
        item_editor=None,
        panels=SimpleNamespace(dispatch_input=lambda _key, _mods: False),
        search=None,
        _find_everything_open=False,
        asset_place_active=False,
        asset_browser_active=False,
        scene_switcher_active=False,
        entity_panels_active=False,
        dialogue_panel_active=False,
        dialogue_editing=False,
        animation_active=False,
        animation_editing=False,
        palette_active=False,
        palette_filter_active=False,
        hierarchy_active=False,
        shape_edit_mode=False,
        tile_panel_active=False,
        occluder_tool_active=False,
        lights_tool_active=False,
        tool_mode="SELECT",
        selected_entity=None,
        window=window,
    )


def test_quest_editor_text_input_routes_only_when_quests_tab_and_edit_mode() -> None:
    controller = _controller()

    editor_input_text_handlers.handle_text_input(controller, "x")

    assert controller.quest_editor.calls == [("text", "x")]
    wrong_tab = _controller(right_tab="Prefabs")
    editor_input_text_handlers.handle_text_input(wrong_tab, "x")
    assert wrong_tab.quest_editor.calls == []
    inactive = _controller(edit_mode=False)
    editor_input_text_handlers.handle_text_input(inactive, "x")
    assert inactive.quest_editor.calls == []
    missing = _controller(include_quest_editor=False)
    editor_input_text_handlers.handle_text_input(missing, "x")


def test_quest_editor_key_routes_only_when_quests_tab_and_edit_mode() -> None:
    controller = _controller()

    handled = editor_input_key_handlers.handle_pre_routed_keys(controller, optional_arcade.arcade.key.BACKSPACE, 0)

    assert handled is True
    assert controller.quest_editor.calls == [("key", (optional_arcade.arcade.key.BACKSPACE, 0))]
    wrong_tab = _controller(right_tab="History")
    assert editor_input_key_handlers.handle_pre_routed_keys(wrong_tab, optional_arcade.arcade.key.BACKSPACE, 0) is False
    assert wrong_tab.quest_editor.calls == []
    inactive = _controller(edit_mode=False)
    assert editor_input_key_handlers.handle_pre_routed_keys(inactive, optional_arcade.arcade.key.BACKSPACE, 0) is False
    assert inactive.quest_editor.calls == []


def test_quest_editor_tab_cycles_focus_when_quests_tab_and_edit_mode() -> None:
    controller = _controller()

    handled = editor_input_key_handlers.handle_pre_routed_keys(controller, optional_arcade.arcade.key.TAB, 0)
    shifted = editor_input_key_handlers.handle_pre_routed_keys(
        controller,
        optional_arcade.arcade.key.TAB,
        optional_arcade.arcade.key.MOD_SHIFT,
    )

    assert handled is True
    assert shifted is True
    assert controller.quest_editor.calls == [("cycle", "forward"), ("cycle", "backward")]


def test_quest_editor_escape_routes_to_controller_when_quests_tab_and_edit_mode() -> None:
    controller = _controller()

    handled = editor_input_key_handlers.handle_pre_routed_keys(controller, optional_arcade.arcade.key.ESCAPE, 0)

    assert handled is True
    assert controller.quest_editor.calls == [("key", (optional_arcade.arcade.key.ESCAPE, 0))]


def test_quest_editor_click_routes_only_when_quests_tab_and_edit_mode(monkeypatch: pytest.MonkeyPatch) -> None:
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
    assert controller.quest_editor.calls == [("click", (12.0, 34.0))]
    wrong_tab = _controller(right_tab="Problems")
    assert dispatch_database_form_click(wrong_tab, 12.0, 34.0) is False
    assert wrong_tab.quest_editor.calls == []
