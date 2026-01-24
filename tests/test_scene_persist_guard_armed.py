from __future__ import annotations

import arcade


def test_scene_persist_hotkey_requires_arming(capsys) -> None:
    from engine.input_runtime import capture as input_capture

    class _Console:
        active = False

        def toggle(self) -> None:
            raise AssertionError("not used")

        def process_key(self, _key: int, _mod: int) -> bool:
            return False

    class _UI:
        input_blocked = False

        def on_key_press(self, _key: int, _mod: int) -> bool:
            return False

    class _Result:
        ok = True
        path = "scenes/foo.json"

    class _Window:
        show_debug = True
        console_controller = _Console()
        ui_controller = _UI()
        scene_persist_armed = False

        def __init__(self) -> None:
            self._persist_called = 0

        def persist_scene_to_disk(self):
            self._persist_called += 1
            return _Result()

    window = _Window()
    controller = type("C", (), {"window": window})()

    assert input_capture.handle_key_press(controller, arcade.key.S, arcade.key.MOD_CTRL) is True
    assert window._persist_called == 0
    assert capsys.readouterr().out.strip() == "SCENE_PERSIST (not armed)"

    assert input_capture.handle_key_press(controller, arcade.key.S, arcade.key.MOD_CTRL | arcade.key.MOD_SHIFT) is True
    assert window.scene_persist_armed is True
    assert capsys.readouterr().out.strip() == "SCENE_PERSIST_ARMED on"

    assert input_capture.handle_key_press(controller, arcade.key.S, arcade.key.MOD_CTRL) is True
    assert window._persist_called == 1
    assert capsys.readouterr().out.strip() == "SCENE_PERSIST ok path=scenes/foo.json"

