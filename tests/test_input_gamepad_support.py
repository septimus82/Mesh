from __future__ import annotations

import pytest

from engine.input import InputManager
from engine.input_controller import map_gamepad_state, read_gamepad_state


class _StubButton:
    def __init__(self, pressed: bool) -> None:
        self.pressed = pressed


class _StubController:
    def __init__(self, *, leftx: float, lefty: float, buttons: list[_StubButton]) -> None:
        self.leftx = leftx
        self.lefty = lefty
        self.buttons = buttons


@pytest.mark.fast
def test_gamepad_deadzone_mapping() -> None:
    actions, axis_values, active = map_gamepad_state(0.1, 0.0, set(), deadzone=0.2)
    assert actions == set()
    assert axis_values[("move_left", "move_right")] == 0.0
    assert axis_values[("move_down", "move_up")] == 0.0
    assert active is False

    actions, axis_values, active = map_gamepad_state(0.6, 0.0, set(), deadzone=0.2)
    assert "move_right" in actions
    assert axis_values[("move_left", "move_right")] == 0.6
    assert active is True

    actions, axis_values, _ = map_gamepad_state(0.0, -0.7, set(), deadzone=0.2)
    assert "move_up" in actions
    assert axis_values[("move_down", "move_up")] == 0.7


@pytest.mark.fast
def test_gamepad_button_mapping() -> None:
    actions, _, _ = map_gamepad_state(
        0.0,
        0.0,
        {"a", "b", "x", "y", "start"},
        deadzone=0.2,
    )
    assert "interact" in actions
    assert "toggle_help" in actions
    assert "attack" in actions
    assert "show_inventory" in actions
    assert "pause_menu" in actions


@pytest.mark.fast
def test_gamepad_stub_controller_mapping() -> None:
    buttons = [
        _StubButton(True),   # A
        _StubButton(False),  # B
        _StubButton(False),  # X
        _StubButton(False),  # Y
        _StubButton(False),  # LB
        _StubButton(False),  # RB
        _StubButton(False),  # Back
        _StubButton(True),   # Start
    ]
    controller = _StubController(leftx=0.5, lefty=-0.5, buttons=buttons)
    axis_x, axis_y, buttons_down, dpad_x, dpad_y = read_gamepad_state(controller)
    assert axis_x == 0.5
    assert axis_y == -0.5
    assert dpad_x == 0.0
    assert dpad_y == 0.0
    assert buttons_down == {"a", "start"}

    actions, _, active = map_gamepad_state(axis_x, axis_y, buttons_down, deadzone=0.2)
    assert {"move_right", "move_up", "interact", "pause_menu"}.issubset(actions)
    assert active is True


@pytest.mark.fast
def test_keyboard_still_drives_axis_with_gamepad_connected() -> None:
    manager = InputManager()
    manager.bind("move_left", 1)
    manager.bind("move_right", 2)
    manager.press(1)
    manager.set_gamepad_state(
        actions_down=(),
        axis_values={
            ("move_left", "move_right"): 0.0,
            ("move_down", "move_up"): 0.0,
        },
        supported_actions={"move_left", "move_right", "move_down", "move_up"},
        source_active=False,
    )
    assert manager.get_axis("move_left", "move_right") == -1.0


@pytest.mark.fast
def test_input_source_switching() -> None:
    manager = InputManager()
    assert manager.input_source == "keyboard_mouse"

    manager.set_gamepad_state(
        actions_down={"interact"},
        axis_values={("move_left", "move_right"): 0.0, ("move_down", "move_up"): 0.0},
        supported_actions={"interact"},
        source_active=True,
    )
    assert manager.input_source == "gamepad"

    manager.press(10)
    assert manager.input_source == "keyboard_mouse"
