from __future__ import annotations

import pytest

from engine.input_hints import get_action_hint, set_keyboard_hints


@pytest.mark.fast
def test_gamepad_hints() -> None:
    assert get_action_hint("interact", "gamepad") == "A"
    assert get_action_hint("attack", "gamepad") == "X"
    assert get_action_hint("pause_menu", "gamepad") == "Start"


@pytest.mark.fast
def test_keyboard_hint_fallbacks() -> None:
    set_keyboard_hints({"interact": ["E"]})
    assert get_action_hint("interact", "keyboard_mouse") == "E"
    assert get_action_hint("attack", "keyboard_mouse") != ""


@pytest.mark.fast
def test_unknown_action_returns_empty() -> None:
    assert get_action_hint("unknown_action", "gamepad") == ""
