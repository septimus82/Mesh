from __future__ import annotations

from types import SimpleNamespace

import pytest

import engine.optional_arcade as optional_arcade
from engine.ui_overlays.pause_menu import PauseMenu
from tests._typing import as_any

pytestmark = [pytest.mark.fast]


class _StubAudio:
    def play_sound(self, _path: str) -> None:
        return


class _StubSaveManager:
    def list_saves(self) -> list[str]:
        return []

    def save_game(self, _slot: str) -> bool:
        return True

    def load_game(self, _slot: str) -> bool:
        return True


def _window() -> SimpleNamespace:
    return SimpleNamespace(
        width=800,
        height=600,
        paused=True,
        audio=_StubAudio(),
        save_manager=_StubSaveManager(),
    )


def test_pause_menu_main_uses_widgets_and_click_matches_enter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)

    menu_enter = PauseMenu(as_any(_window()))
    menu_enter.visible = True
    menu_enter.state = "main"
    menu_enter.selected_index = 1  # Settings
    handled_enter = menu_enter.on_key_press(optional_arcade.arcade.key.ENTER, 0)
    assert handled_enter is True
    assert menu_enter.state == "settings"

    menu_click = PauseMenu(as_any(_window()))
    menu_click.visible = True
    menu_click.state = "main"
    menu_click.draw()
    assert menu_click._main_menu_buttons
    target = menu_click._main_menu_buttons[1]
    assert target.last_rect is not None
    rect = target.last_rect
    handled_click = as_any(menu_click).on_mouse_press(rect.center_x, rect.center_y, 1, 0)
    assert handled_click is True
    assert menu_click.state == "settings"
