"""Input-dispatch contract for debug monster breeding hotkey."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import engine.optional_arcade as optional_arcade
from engine.config import load_config
from engine.game_runtime import input_dispatch
from tests._typing import as_any
from tests.test_monster_companion_battle import _window

pytestmark = pytest.mark.fast


def test_f10_breeds_party_when_debug_mode_enabled() -> None:
    window = _window()
    window.engine_config = load_config("config.json")
    window.engine_config.debug_mode = True
    window.debug_breed_first_party_pair = MagicMock(return_value=True)

    input_dispatch.on_key_press(
        as_any(window),
        optional_arcade.arcade.key.F10,
        0,
    )

    window.debug_breed_first_party_pair.assert_called_once_with()


def test_f10_does_not_breed_when_debug_mode_disabled() -> None:
    window = _window()
    window.engine_config = load_config("config.json")
    window.engine_config.debug_mode = False
    window.debug_breed_first_party_pair = MagicMock(return_value=True)

    input_dispatch.on_key_press(
        as_any(window),
        optional_arcade.arcade.key.F10,
        0,
    )

    window.debug_breed_first_party_pair.assert_not_called()
