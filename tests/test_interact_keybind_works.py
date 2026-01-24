from __future__ import annotations

import arcade


class _Console:
    active = False

    def toggle(self) -> None:  # pragma: no cover
        return

    def process_key(self, _key: int, _mod: int) -> bool:  # pragma: no cover
        return False


class _UI:
    input_blocked = False

    def on_key_press(self, _key: int, _mod: int) -> bool:  # pragma: no cover
        return False


class _Editor:
    active = False


class _Controller:
    def __init__(self, window, manager) -> None:
        self.window = window
        self.manager = manager
        self._keys: set[int] = set()

    def is_input_locked(self) -> bool:
        return False


def test_interact_uses_configured_keybind(monkeypatch) -> None:
    from engine.input import InputManager
    from engine.input_runtime import capture as input_capture
    import engine.interaction

    monkeypatch.setattr(engine.interaction, "perform_interaction", lambda *_a, **_k: True)

    class _Window:
        show_debug = False
        console_controller = _Console()
        ui_controller = _UI()
        editor_controller = _Editor()
        cutscene_controller = None

    manager = InputManager()
    manager.bind("interact", arcade.key.K)
    controller = _Controller(_Window(), manager)

    assert input_capture.handle_key_press(controller, arcade.key.K, 0) is True
    assert bool(getattr(controller.window, "_mesh_interact_consumed", False)) is True
    assert arcade.key.K in controller._keys
    assert arcade.key.K in controller.manager.get_keys_down()
