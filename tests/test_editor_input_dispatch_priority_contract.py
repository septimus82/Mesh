from __future__ import annotations

from types import SimpleNamespace

import pytest

import engine.input_runtime.capture_key_router as capture_router
import engine.optional_arcade as optional_arcade
from engine.game_runtime import input_dispatch
from engine.input_runtime import capture_key_router_handlers_global as global_handlers
from engine.input_runtime.capture_focus_query import get_capture_focus_snapshot
from tests._typing import as_any

pytestmark = [pytest.mark.fast]


def _window(editor: object, calls: list[str]) -> SimpleNamespace:
    return SimpleNamespace(
        editor_controller=editor,
        show_debug=False,
        command_palette_enabled=False,
        command_palette_prompt_active=False,
        console_controller=SimpleNamespace(active=False),
        ui_controller=SimpleNamespace(
            input_blocked=False,
            on_key_press=lambda *_args: calls.append("ui") or True,
        ),
        settings_overlay=SimpleNamespace(toggle=lambda: calls.append("settings")),
        input_controller=SimpleNamespace(on_key_press=lambda *_args: calls.append("input")),
        engine_config=SimpleNamespace(debug_mode=False),
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

    input_dispatch.on_key_press(as_any(_window(editor, calls)), optional_arcade.arcade.key.A, 0)

    assert calls == ["editor", "input"]


def test_f4_directly_toggles_editor_before_input_controller() -> None:
    calls: list[str] = []
    editor = SimpleNamespace(active=False, toggle=lambda: calls.append("toggle"))

    input_dispatch.on_key_press(as_any(_window(editor, calls)), optional_arcade.arcade.key.F4, 0)

    assert calls == ["toggle"]


def test_f4_direct_toggle_ignores_capslock_modifier() -> None:
    calls: list[str] = []
    editor = SimpleNamespace(active=False, toggle=lambda: calls.append("toggle"))

    input_dispatch.on_key_press(
        as_any(_window(editor, calls)),
        optional_arcade.arcade.key.F4,
        optional_arcade.arcade.key.MOD_CAPSLOCK,
    )

    assert calls == ["toggle"]


def test_f4_direct_toggle_ignores_numlock_modifier() -> None:
    calls: list[str] = []
    editor = SimpleNamespace(active=False, toggle=lambda: calls.append("toggle"))

    input_dispatch.on_key_press(
        as_any(_window(editor, calls)),
        optional_arcade.arcade.key.F4,
        optional_arcade.arcade.key.MOD_NUMLOCK,
    )

    assert calls == ["toggle"]


def test_f4_direct_toggle_blocks_real_shift_modifier() -> None:
    calls: list[str] = []
    editor = SimpleNamespace(active=False, toggle=lambda: calls.append("toggle"))

    input_dispatch.on_key_press(
        as_any(_window(editor, calls)),
        optional_arcade.arcade.key.F4,
        optional_arcade.arcade.key.MOD_SHIFT,
    )

    assert calls == ["ui"]


def test_shift_f5_toggles_creator_mode_when_editor_active_before_input_controller() -> None:
    calls: list[str] = []
    creator = SimpleNamespace(active=False)

    def toggle_creator() -> None:
        creator.active = not creator.active
        calls.append("creator")

    editor = SimpleNamespace(
        active=True,
        creator_mode=creator,
        toggle_creator_mode=toggle_creator,
        build_session=SimpleNamespace(is_running=False),
        play_session=SimpleNamespace(is_playing=False),
        handle_input=lambda *_args: calls.append("editor") or False,
    )

    input_dispatch.on_key_press(
        as_any(_window(editor, calls)),
        optional_arcade.arcade.key.F5,
        optional_arcade.arcade.key.MOD_SHIFT,
    )

    assert calls == ["creator"]
    assert creator.active is True


def test_shift_f5_creator_toggle_ignores_capslock_when_editor_active() -> None:
    calls: list[str] = []
    creator = SimpleNamespace(active=False)

    def toggle_creator() -> None:
        creator.active = not creator.active
        calls.append("creator")

    editor = SimpleNamespace(
        active=True,
        creator_mode=creator,
        toggle_creator_mode=toggle_creator,
        build_session=SimpleNamespace(is_running=False),
        play_session=SimpleNamespace(is_playing=False),
        handle_input=lambda *_args: calls.append("editor") or False,
    )

    input_dispatch.on_key_press(
        as_any(_window(editor, calls)),
        optional_arcade.arcade.key.F5,
        optional_arcade.arcade.key.MOD_SHIFT | optional_arcade.arcade.key.MOD_CAPSLOCK,
    )

    assert calls == ["creator"]
    assert creator.active is True


def test_f5_editor_active_reaches_quick_save_route(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    editor = SimpleNamespace(
        active=True,
        toggle_creator_mode=lambda: calls.append("creator"),
        build_session=SimpleNamespace(is_running=False),
        play_session=SimpleNamespace(is_playing=False),
        handle_input=lambda *_args: calls.append("editor") or False,
    )
    window = _window(editor, calls)

    def savegame_save(_window: object) -> bool:
        calls.append("capture.savegame.save")
        return True

    def route_through_capture(key: int, modifiers: int) -> None:
        controller = SimpleNamespace(window=window, manager=SimpleNamespace(is_key_bound_to_action=lambda *_args: False))
        snapshot = get_capture_focus_snapshot(controller, modifiers)
        if capture_router.route_and_dispatch(controller, key, modifiers, snapshot):
            calls.append("input")

    window.input_controller = SimpleNamespace(on_key_press=route_through_capture)
    monkeypatch.setattr(global_handlers, "_handle_savegame_save", savegame_save)

    input_dispatch.on_key_press(as_any(window), optional_arcade.arcade.key.F5, 0)

    assert calls == ["editor", "capture.savegame.save", "input"]


def test_f5_editor_inactive_still_reaches_existing_input_controller_path() -> None:
    calls: list[str] = []
    editor = SimpleNamespace(active=False)
    window = _window(editor, calls)
    window.ui_controller = SimpleNamespace(on_key_press=lambda *_args: False)

    input_dispatch.on_key_press(as_any(window), optional_arcade.arcade.key.F5, 0)

    assert calls == ["input"]
