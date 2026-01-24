import arcade


class _DummyConsole:
    active = False

    def process_key(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        return False

    def toggle(self) -> None:
        return


class _DummyUI:
    def __init__(self, *, input_blocked: bool) -> None:
        self._input_blocked = bool(input_blocked)

    @property
    def input_blocked(self) -> bool:
        return self._input_blocked

    def on_key_press(self, key: int, modifiers: int) -> bool:  # noqa: ARG002
        return False


class _DummyEditor:
    active = False


class _DummyWindow:
    def __init__(self, *, ui_blocked: bool) -> None:
        self.console_controller = _DummyConsole()
        self.ui_controller = _DummyUI(input_blocked=ui_blocked)
        self.editor_controller = _DummyEditor()
        self.show_debug = False


class _DummyManager:
    def __init__(self) -> None:
        self.pressed: list[int] = []

    def press(self, key: int) -> None:
        self.pressed.append(int(key))

    def is_key_bound_to_action(self, action: str, key: int) -> bool:  # noqa: ARG002
        return False


class _DummyController:
    def __init__(self, *, ui_blocked: bool) -> None:
        self.window = _DummyWindow(ui_blocked=ui_blocked)
        self.manager = _DummyManager()
        self._keys: set[int] = set()

    def is_input_locked(self) -> bool:
        return False


def test_interact_key_is_recorded_when_ui_blocks_input() -> None:
    """
    When UI blocks input (e.g. DialogueBox visible), the Interact key should still
    be recorded by InputManager so behaviours can react (advance dialogue, submit choices).
    """

    from engine.input_runtime.capture_runtime import handle_key_press

    controller = _DummyController(ui_blocked=True)
    consumed = handle_key_press(controller, arcade.key.E, 0)
    assert consumed is False
    assert int(arcade.key.E) in controller.manager.pressed
    assert int(arcade.key.E) in controller._keys

