from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

import engine.optional_arcade as optional_arcade
from engine.action_runtime.registry import get_required_actions
from engine.input import InputManager
from engine.input_controller import InputController
from engine.input_runtime.capture_key_router_model import KeyCombo, build_route_table, resolve_route
from engine.input_runtime.capture_runtime_focus_model import SCOPE_GLOBAL, CaptureFocusSnapshot
from tests._typing import as_any

pytestmark = [pytest.mark.fast]


class _StubWindow:
    def __init__(
        self,
        *,
        input_bindings: dict[str, list[str]] | None = None,
        show_debug: bool = False,
    ) -> None:
        self.engine_config = SimpleNamespace(input_bindings=input_bindings)
        self.show_debug = bool(show_debug)
        self.scene_persist_armed = False

        self.command_palette_enabled = False
        self.command_palette_prompt_active = False

        self.console_controller = SimpleNamespace(
            active=False,
            process_key=lambda _k, _m: False,
            toggle=lambda: None,
        )
        self.ui_controller = SimpleNamespace(
            input_blocked=False,
            on_key_press=lambda _k, _m: False,
        )
        self.editor_controller = SimpleNamespace(
            active=False,
            panels=None,
            keybinds=None,
            project_explorer=None,
            session=None,
            dock=None,
            toggle=lambda: None,
        )
        self.settings_overlay = None

        self.capture_state = None
        self.tile_paint_state = None
        self.entity_paint_state = None
        self.entity_select_state = None
        self.authoring_selected_entity_id = None

        self.perf_overlay = None
        self.profiler_overlay = None
        self.encounter_debug_overlay = None
        self.scene_inspector_overlay = None

        self.undo = lambda: None
        self.redo = lambda: None
        self.console_log = lambda _msg: None


def _global_focus_snapshot() -> CaptureFocusSnapshot:
    return CaptureFocusSnapshot(
        is_confirm_modal_open=False,
        is_context_menu_open=False,
        is_keybinds_recording=False,
        is_keybinds_open=False,
        is_inline_rename_active=False,
        is_command_palette_open=False,
        is_command_palette_prompt_active=False,
        is_console_active=False,
        is_project_explorer_focused=False,
        is_problems_focused=False,
        is_palette_mode_enabled=False,
        is_capture_mode_enabled=False,
        is_tile_paint_enabled=False,
        is_entity_paint_enabled=False,
        is_entity_select_active=False,
        is_authoring_selected=False,
        show_debug=False,
        editor_active=False,
        ui_blocked=False,
        scene_persist_armed=False,
        ctrl=False,
        alt=False,
        shift=False,
    )


def test_bind_default_actions_include_arrow_movement_and_pause() -> None:
    manager = InputManager()
    manager.bind_default_actions(optional_arcade.arcade)

    key = optional_arcade.arcade.key
    assert manager.is_key_bound_to_action("move_up", key.UP) is True
    assert manager.is_key_bound_to_action("move_down", key.DOWN) is True
    assert manager.is_key_bound_to_action("move_left", key.LEFT) is True
    assert manager.is_key_bound_to_action("move_right", key.RIGHT) is True
    assert manager.is_key_bound_to_action("pause_menu", key.ESCAPE) is True


def test_capture_route_falls_through_when_no_action_taken() -> None:
    window = _StubWindow(input_bindings=None, show_debug=False)
    controller = InputController(as_any(window))
    key = optional_arcade.arcade.key.P  # Routed to perf toggle.

    consumed = controller.on_key_press(key, 0)

    assert consumed is False
    assert controller.manager.is_key_down(key) is True


def test_pause_menu_action_reachable_from_keyboard() -> None:
    window = _StubWindow(input_bindings={"move_up": ["W"]}, show_debug=False)
    controller = InputController(as_any(window))
    key = optional_arcade.arcade.key.ESCAPE
    dispatched: list[str] = []

    with patch("engine.input_controller.dispatch_action", side_effect=lambda _w, action: dispatched.append(str(action)) or True):
        controller.on_key_press(key, 0)
        controller.update(1 / 60.0)

    assert "pause_menu" in dispatched


def test_save_load_actions_reachable_in_gameplay_scope() -> None:
    window = _StubWindow(
        input_bindings={
            "save_game": [],
            "quick_load": ["F9"],
            "quickload_last_save": ["F10"],
        },
        show_debug=False,
    )
    controller = InputController(as_any(window))
    key = optional_arcade.arcade.key
    dispatched: list[str] = []

    def _tick_key(key_code: int, modifiers: int) -> None:
        controller.on_key_press(key_code, modifiers)
        controller.update(1 / 60.0)
        controller.on_key_release(key_code, modifiers)
        controller.update(1 / 60.0)

    with patch("engine.actions.dispatch_action", side_effect=lambda _w, action: dispatched.append(str(action)) or True):
        _tick_key(key.F5, key.MOD_CTRL)
        _tick_key(key.F6, key.MOD_CTRL)
        _tick_key(key.F7, key.MOD_CTRL)

    assert "save_game" in dispatched
    assert "quick_load" in dispatched
    assert "quickload_last_save" in dispatched


def test_save_game_is_ctrl_f5_routed_action_and_plain_f5_remains_quick_save() -> None:
    key = optional_arcade.arcade.key
    snapshot = _global_focus_snapshot()
    routes = build_route_table()

    assert (
        resolve_route([SCOPE_GLOBAL], KeyCombo(key=key.F5, mods=key.MOD_CTRL), routes, snapshot)
        == "capture.action.save_game"
    )
    assert (
        resolve_route([SCOPE_GLOBAL], KeyCombo(key=key.F5, mods=0), routes, snapshot)
        == "capture.savegame.save"
    )
    assert "save_game" in get_required_actions()


def test_ctrl_f5_dispatches_save_game_once_without_plain_quick_save(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _StubWindow(input_bindings={"save_game": [], "quick_save": ["F5"]}, show_debug=False)
    controller = InputController(as_any(window))
    key = optional_arcade.arcade.key
    dispatched: list[str] = []

    def _plain_quick_save_called(_window: object) -> object:
        raise AssertionError("Ctrl+F5 must not execute the plain F5 quick-save path")

    monkeypatch.setattr("engine.savegame.capture_savegame_from_window", _plain_quick_save_called)
    with patch("engine.actions.dispatch_action", side_effect=lambda _w, action: dispatched.append(str(action)) or True):
        assert controller.on_key_press(key.F5, key.MOD_CTRL) is True
        controller.on_key_release(key.F5, key.MOD_CTRL)

    assert dispatched == ["save_game"]


def test_ctrl_f5_route_ignores_lock_key_modifiers(monkeypatch: pytest.MonkeyPatch) -> None:
    window = _StubWindow(input_bindings={"save_game": []}, show_debug=False)
    controller = InputController(as_any(window))
    key = optional_arcade.arcade.key
    dispatched: list[str] = []
    lock_mods = (
        getattr(key, "MOD_CAPSLOCK", 0)
        | getattr(key, "MOD_NUMLOCK", 0)
        | getattr(key, "MOD_SCROLLLOCK", 0)
    )

    monkeypatch.setattr(
        "engine.savegame.capture_savegame_from_window",
        lambda _window: (_ for _ in ()).throw(AssertionError("plain quick-save path should not run")),
    )
    with patch("engine.actions.dispatch_action", side_effect=lambda _w, action: dispatched.append(str(action)) or True):
        assert controller.on_key_press(key.F5, key.MOD_CTRL | lock_mods) is True

    assert dispatched == ["save_game"]
