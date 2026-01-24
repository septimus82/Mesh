from __future__ import annotations

from unittest.mock import MagicMock, patch

from engine.input_controller import InputController


def test_dispatch_order_preserves_bound_action_iteration_order() -> None:
    window = MagicMock()
    window.ui_controller = MagicMock()
    window.ui_controller.input_blocked = False
    window.engine_config = MagicMock()
    window.engine_config.input_bindings = None
    window.console_controller = MagicMock(active=False)
    window.editor_controller = MagicMock(active=False)
    window.player_hud = MagicMock()

    controller = InputController(window)
    controller.manager = MagicMock()
    controller.manager.update = MagicMock()
    controller.manager.get_bound_action_names.return_value = ["toggle_help", "show_inventory"]
    controller.manager.was_action_pressed.return_value = True

    calls: list[str] = []

    def _dispatch(_window, name: str) -> bool:
        calls.append(str(name))
        return True

    with patch("engine.input_controller.dispatch_action", side_effect=_dispatch):
        controller.update(0.016)

    assert calls == ["toggle_help", "show_inventory"]

