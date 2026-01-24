from __future__ import annotations

import engine.optional_arcade as optional_arcade

from engine.console_controller import ConsoleController
from engine.input import InputManager


def test_console_return_executes_command() -> None:
    class _Lighting:
        def get_lighting_stats(self):
            return {
                "shadows_mode": "none",
                "occluder_count": 1,
                "culled_occluder_count": 1,
                "shadow_poly_count": 1,
                "mask_rendered": False,
            }

    class _Window:
        def __init__(self) -> None:
            self.input = InputManager()
            self.lighting = _Lighting()

    window = _Window()
    console = ConsoleController(window)
    console.toggle()
    window.input.set_text_buffer("lighting_stats")

    assert console.process_key(optional_arcade.arcade.key.RETURN, 0) is True
    assert any("lighting_stats" in line for line in console.lines)
    assert any("[Lighting]" in line and "shadows_mode=" in line for line in console.lines)

