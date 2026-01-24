from __future__ import annotations

import engine.optional_arcade as optional_arcade


class _Manager:
    def __init__(self) -> None:
        self.pressed: list[int] = []

    def press(self, key: int) -> None:
        self.pressed.append(int(key))


class _Console:
    active = False

    def toggle(self) -> None:  # pragma: no cover
        return

    def process_key(self, _key: int, _mod: int) -> bool:  # pragma: no cover
        return False


class _UI:
    def on_key_press(self, _key: int, _mod: int) -> bool:
        return False


class _Editor:
    active = False


def test_capture_mode_consumes_interact_key() -> None:
    from engine.capture_mode import CaptureState
    from engine.input_runtime import capture as input_capture

    class _Window:
        show_debug = True
        capture_state = CaptureState(enabled=True)
        console_controller = _Console()
        ui_controller = _UI()
        editor_controller = _Editor()

    controller = type("C", (), {"window": _Window(), "manager": _Manager(), "_keys": set()})()
    assert input_capture.handle_key_press(controller, optional_arcade.arcade.key.E, 0) is True
    assert controller.manager.pressed == []

