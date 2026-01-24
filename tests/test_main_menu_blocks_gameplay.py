from __future__ import annotations

import types
from unittest.mock import MagicMock

import arcade

from engine.input_controller import InputController
from engine.ui import MainMenuOverlay
from engine.ui_controller import UIController


def test_main_menu_blocks_gameplay(monkeypatch) -> None:
    window = types.SimpleNamespace()
    window.width = 800
    window.height = 600
    window.paused = False
    window.show_debug = False
    window.engine_config = types.SimpleNamespace(
        input_bindings={
            "move_up": ["W"],
            "interact": ["E"],
        }
    )
    window.config_path = "config.json"
    window.player_hud = types.SimpleNamespace(enqueue_toast=MagicMock())
    window.audio = types.SimpleNamespace(play_sound=MagicMock())

    class _Console:
        active = False

        def toggle(self) -> None:
            return

        def process_key(self, _key: int, _mod: int) -> bool:
            return False

    window.console_controller = _Console()
    window.editor_controller = types.SimpleNamespace(active=False)

    window.ui_controller = UIController(window)  # type: ignore[arg-type]

    controller = InputController(window)  # type: ignore[arg-type]
    window.input_controller = controller

    menu = MainMenuOverlay(window)  # type: ignore[arg-type]
    menu.open()
    window.ui_controller.register_ui_element(menu)

    mock_dispatch = MagicMock(return_value=True)
    monkeypatch.setattr("engine.input_controller.dispatch_action", mock_dispatch)

    mock_interact = MagicMock(return_value=False)
    monkeypatch.setattr("engine.interaction.perform_interaction", mock_interact)

    controller.on_key_press(arcade.key.W, 0)
    controller.update(0.016)
    assert mock_dispatch.call_count == 0

    controller.on_key_press(arcade.key.E, 0)
    controller.update(0.016)
    assert mock_interact.call_count == 0

