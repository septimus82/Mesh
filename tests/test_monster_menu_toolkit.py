from __future__ import annotations

import types
from unittest.mock import MagicMock

import pytest

import engine.optional_arcade as optional_arcade
from engine.game_runtime import input_dispatch
from engine.game_state_controller import GameState
from engine.monster.collection import MONSTER_INSTANCES_KEY, MONSTER_PARTY_KEY
from engine.monster.party_menu import MonsterPartyScreen, open_monster_party_view
from engine.ui.menu_toolkit import ConfirmModalScreen, MenuRenderer, MenuStackOverlay, SelectableItem, SelectableListScreen
from engine.ui.widgets import Rect
from engine.ui_controller import UIController
from tests._typing import as_any

pytestmark = pytest.mark.fast


class _Console:
    active = False

    def process_key(self, _key: int, _modifiers: int) -> bool:
        return False


class _CountingScreen:
    title = "Counting"

    def __init__(self) -> None:
        self.keys: list[int] = []
        self.draws: list[bool] = []

    def draw(self, _renderer: MenuRenderer, _bounds: Rect, *, active: bool) -> None:
        self.draws.append(active)

    def on_key_press(self, key: int, _modifiers: int, _stack: MenuStackOverlay) -> bool:
        self.keys.append(key)
        return True


def _window() -> types.SimpleNamespace:
    window = types.SimpleNamespace()
    window.width = 1280
    window.height = 720
    window.editor_controller = types.SimpleNamespace(active=False)
    window.console_controller = _Console()
    window.ui_controller = UIController(as_any(window))
    window.input_controller = MagicMock()
    window.game_over = False
    window.engine_config = types.SimpleNamespace(debug_mode=False)
    window.game_state_controller = types.SimpleNamespace(state=GameState())
    window.console_log = MagicMock()
    return window


def test_menu_stack_routes_keys_only_to_top_and_returns_to_lower() -> None:
    window = _window()
    stack = MenuStackOverlay(window)
    lower = _CountingScreen()
    upper = _CountingScreen()
    window.ui_controller.register_ui_element(stack)

    stack.push(lower)
    assert window.ui_controller.on_key_press(optional_arcade.arcade.key.DOWN, 0) is True
    stack.push(upper)
    assert window.ui_controller.on_key_press(optional_arcade.arcade.key.UP, 0) is True

    assert lower.keys == [optional_arcade.arcade.key.DOWN]
    assert upper.keys == [optional_arcade.arcade.key.UP]

    assert stack.pop() is upper
    assert window.ui_controller.on_key_press(optional_arcade.arcade.key.ENTER, 0) is True
    assert lower.keys[-1] == optional_arcade.arcade.key.ENTER


def test_focus_navigation_activation_and_escape_pop() -> None:
    window = _window()
    stack = MenuStackOverlay(window)
    activated: list[str] = []
    screen = SelectableListScreen(
        title="Party",
        items=[
            SelectableItem("a", "Alpha", ("Level: 1",)),
            SelectableItem("b", "Bravo", ("Level: 2",)),
        ],
        on_activate=lambda item: activated.append(item.id),
    )
    stack.push(screen)
    window.ui_controller.register_ui_element(stack)

    assert window.ui_controller.on_key_press(optional_arcade.arcade.key.DOWN, 0) is True
    assert screen.focused_item is not None
    assert screen.focused_item.id == "b"
    assert window.ui_controller.on_key_press(optional_arcade.arcade.key.ENTER, 0) is True
    assert activated == ["b"]
    assert screen.activated_item_id == "b"
    assert window.ui_controller.on_key_press(optional_arcade.arcade.key.ESCAPE, 0) is True
    assert stack.screens == []


def test_confirm_modal_blocks_screen_beneath_it() -> None:
    window = _window()
    stack = MenuStackOverlay(window)
    lower = _CountingScreen()
    confirmed: list[bool] = []
    modal = ConfirmModalScreen(title="Confirm", message="Continue?", on_confirm=confirmed.append)
    stack.push(lower)
    stack.push(modal)
    window.ui_controller.register_ui_element(stack)

    assert window.ui_controller.on_key_press(optional_arcade.arcade.key.DOWN, 0) is True
    assert lower.keys == []
    assert modal.selected_index == 1
    assert window.ui_controller.on_key_press(optional_arcade.arcade.key.ENTER, 0) is True

    assert confirmed == [False]
    assert stack.screens == [lower]
    assert lower.keys == []


def test_party_view_opens_from_input_dispatch_and_lists_caught_monsters() -> None:
    window = _window()
    values = window.game_state_controller.state.values
    values[MONSTER_PARTY_KEY] = ["sprout_0001", "shell_0001"]
    values[MONSTER_INSTANCES_KEY] = {
        "sprout_0001": {"species_id": "sproutling", "level": 5, "current_hp": 24, "xp": 200, "known_moves": ["tackle"]},
        "shell_0001": {"species_id": "shelltide", "level": 3, "current_hp": 18, "xp": 80, "known_moves": ["tackle"]},
    }
    window.open_monster_party_view = lambda: open_monster_party_view(window)

    input_dispatch.on_key_press(
        as_any(window),
        optional_arcade.arcade.key.M,
        optional_arcade.arcade.key.MOD_CTRL,
    )

    stack = window.monster_menu_stack
    assert isinstance(stack, MenuStackOverlay)
    assert len(stack.screens) == 1
    screen = stack.screens[-1]
    assert isinstance(screen, MonsterPartyScreen)
    assert [item.id for item in screen.items] == ["sprout_0001", "shell_0001"]
    assert screen.focused_item is not None
    assert "Species: sproutling" in screen.focused_item.detail_lines
    assert "Level: 5" in screen.focused_item.detail_lines
    assert "HP: 24" in screen.focused_item.detail_lines
    assert "XP: 200" in screen.focused_item.detail_lines

    assert window.ui_controller.on_key_press(optional_arcade.arcade.key.DOWN, 0) is True
    assert screen.focused_item is not None
    assert screen.focused_item.id == "shell_0001"
    assert window.ui_controller.on_key_press(optional_arcade.arcade.key.ENTER, 0) is True
    assert screen.activated_item_id == "shell_0001"
    assert window.ui_controller.on_key_press(optional_arcade.arcade.key.ESCAPE, 0) is True
    assert stack.screens == []
