import types

import arcade

from engine.input_controller import InputController
from tests._typing import as_any


class StubHelpOverlay:
    def __init__(self) -> None:
        self.calls = 0

    def toggle(self) -> None:
        self.calls += 1


def test_toggle_help_action_calls_help_overlay_toggle() -> None:
    overlay = StubHelpOverlay()
    window = types.SimpleNamespace(
        engine_config=types.SimpleNamespace(input_bindings=None),
        config_path="config.json",
        help_overlay=overlay,
    )
    controller = InputController(as_any(window))
    controller.manager.press(arcade.key.H)
    controller.update(0.016)
    assert overlay.calls == 1
