from __future__ import annotations

from types import SimpleNamespace

import pytest

import engine.optional_arcade as optional_arcade
from engine.game_runtime import input_dispatch
from tests._typing import as_any

pytestmark = [pytest.mark.fast]


def _window(editor: object, calls: list[str]) -> SimpleNamespace:
    return SimpleNamespace(
        editor_controller=editor,
        console_controller=SimpleNamespace(active=False),
        ui_controller=SimpleNamespace(on_key_press=lambda *_args: calls.append("ui") or True),
        settings_overlay=SimpleNamespace(toggle=lambda: calls.append("settings")),
        input_controller=SimpleNamespace(on_key_press=lambda *_args: calls.append("input")),
        game_over=False,
        paused=False,
        pause_menu=SimpleNamespace(toggle=lambda: calls.append("pause"), visible=False),
        console_log=lambda _message: calls.append("console"),
    )


def test_active_editor_gets_key_before_game_ui_stack() -> None:
    calls: list[str] = []
    editor = SimpleNamespace(
        active=True,
        build_session=SimpleNamespace(is_running=False),
        play_session=SimpleNamespace(is_playing=False),
        handle_input=lambda *_args: calls.append("editor") or True,
    )

    input_dispatch.on_key_press(as_any(_window(editor, calls)), optional_arcade.arcade.key.A, 0)

    assert calls == ["editor"]


def test_escape_in_active_editor_does_not_open_game_settings_when_unhandled() -> None:
    calls: list[str] = []
    editor = SimpleNamespace(
        active=True,
        build_session=SimpleNamespace(is_running=False),
        play_session=SimpleNamespace(is_playing=False),
        handle_input=lambda *_args: calls.append("editor") or False,
    )

    input_dispatch.on_key_press(as_any(_window(editor, calls)), optional_arcade.arcade.key.ESCAPE, 0)

    assert calls == ["editor"]


def test_first_launch_tour_does_not_swallow_unhandled_editor_keys() -> None:
    calls: list[str] = []
    editor = SimpleNamespace(
        active=True,
        build_session=SimpleNamespace(is_running=False),
        play_session=SimpleNamespace(is_playing=False),
        tour=SimpleNamespace(is_active=True),
        handle_input=lambda *_args: calls.append("editor") or True,
    )

    input_dispatch.on_key_press(as_any(_window(editor, calls)), optional_arcade.arcade.key.A, 0)

    assert calls == ["editor"]


def test_first_launch_tour_enter_advances_before_editor_dispatch() -> None:
    calls: list[str] = []
    editor = SimpleNamespace(
        active=True,
        build_session=SimpleNamespace(is_running=False),
        play_session=SimpleNamespace(is_playing=False),
        tour=SimpleNamespace(is_active=True, advance=lambda: calls.append("advance")),
        handle_input=lambda *_args: calls.append("editor") or True,
    )

    input_dispatch.on_key_press(as_any(_window(editor, calls)), optional_arcade.arcade.key.ENTER, 0)

    assert calls == ["advance"]


def test_unhandled_editor_key_reaches_input_controller_without_game_ui_capture() -> None:
    calls: list[str] = []
    editor = SimpleNamespace(
        active=True,
        build_session=SimpleNamespace(is_running=False),
        play_session=SimpleNamespace(is_playing=False),
        handle_input=lambda *_args: calls.append("editor") or False,
    )

    input_dispatch.on_key_press(as_any(_window(editor, calls)), optional_arcade.arcade.key.F4, 0)

    assert calls == ["editor", "input"]
