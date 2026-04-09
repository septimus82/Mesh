from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

import engine.optional_arcade as optional_arcade
from engine.input import InputManager
from engine.input_controller import InputController
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
            "save_game": ["F8"],
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
