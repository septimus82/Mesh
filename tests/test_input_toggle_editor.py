import types

import arcade

from engine.input_controller import InputController


class StubEditorController:
    def __init__(self) -> None:
        self.calls = 0
        self.active = False

    def toggle(self) -> None:
        self.calls += 1


def test_toggle_editor_action_calls_editor_toggle() -> None:
    window = types.SimpleNamespace(
        engine_config=types.SimpleNamespace(input_bindings=None),
        config_path="config.json",
        editor_controller=StubEditorController(),
    )
    controller = InputController(window)  # type: ignore[arg-type]
    controller.manager.press(arcade.key.F4)
    controller.update(0.016)
    assert window.editor_controller.calls == 1
