from __future__ import annotations

from unittest.mock import MagicMock, patch

import arcade

from engine.input_controller import InputController
from engine.ui import UIElement
from engine.ui_controller import UIController


class _BlockingEscElement(UIElement):
    def __init__(self, window) -> None:
        super().__init__(window)
        self.visible = True

    @property
    def blocks_input(self) -> bool:
        return self.visible

    def on_key_press(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        if key == arcade.key.ESCAPE:
            self.visible = False
            return True
        return False


class _NonBlockingElement(UIElement):
    @property
    def blocks_input(self) -> bool:
        return False


def _make_window():
    window = MagicMock()
    window.ui_controller = UIController(window)
    window.console_controller = MagicMock()
    window.console_controller.active = False
    window.console_controller.process_key.return_value = False
    window.editor_controller = MagicMock()
    window.editor_controller.active = False
    window.editor_controller.panels = None  # Prevent spurious MagicMock truthy values
    window.editor_controller.ui_layers = None
    window.editor_controller.keybinds = None
    window.editor_controller.project_explorer = None
    window.engine_config = MagicMock()
    window.engine_config.input_bindings = None
    window.player_hud = MagicMock()
    window.show_debug = False
    window.command_palette_enabled = False
    window.settings_overlay = None  # Prevent ESC from being consumed by settings toggle
    return window


def test_modal_element_blocks_action_dispatch_and_esc_is_consumed() -> None:
    window = _make_window()
    controller = InputController(window)
    controller.manager = MagicMock()
    controller.manager.update = MagicMock()
    controller.manager.get_bound_action_names.return_value = ["move_up"]
    controller.manager.was_action_pressed.return_value = True

    blocking = _BlockingEscElement(window)
    window.ui_controller.register_ui_element(blocking)
    assert window.ui_controller.input_blocked is True

    with patch("engine.input_controller.dispatch_action", return_value=True) as mock_dispatch:
        controller.update(0.016)
        mock_dispatch.assert_not_called()

    controller.manager.press = MagicMock()
    consumed = controller.on_key_press(arcade.key.ESCAPE, 0)
    assert consumed is True
    assert blocking.visible is False
    controller.manager.press.assert_not_called()


def test_non_blocking_element_does_not_block_action_dispatch() -> None:
    window = _make_window()
    controller = InputController(window)
    controller.manager = MagicMock()
    controller.manager.update = MagicMock()
    controller.manager.get_bound_action_names.return_value = ["move_up"]
    controller.manager.was_action_pressed.return_value = True

    window.ui_controller.register_ui_element(_NonBlockingElement(window))
    assert window.ui_controller.input_blocked is False

    with patch("engine.input_controller.dispatch_action", return_value=True) as mock_dispatch:
        controller.update(0.016)
        mock_dispatch.assert_called_once()


def test_whitelisted_action_dispatches_even_when_blocked() -> None:
    window = _make_window()
    controller = InputController(window)
    controller.manager = MagicMock()
    controller.manager.update = MagicMock()
    controller.manager.get_bound_action_names.return_value = ["toggle_help"]
    controller.manager.was_action_pressed.return_value = True

    blocking = _BlockingEscElement(window)
    window.ui_controller.register_ui_element(blocking)
    assert window.ui_controller.input_blocked is True

    with patch("engine.input_controller.dispatch_action", return_value=True) as mock_dispatch:
        controller.update(0.016)
        mock_dispatch.assert_called_once_with(window, "toggle_help")

