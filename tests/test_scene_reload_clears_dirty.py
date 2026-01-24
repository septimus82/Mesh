from __future__ import annotations

import arcade


def test_scene_reload_hotkey_clears_dirty(capsys) -> None:
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

    class _Window:
        show_debug = True
        console_controller = _Console()
        ui_controller = _UI()

        def __init__(self) -> None:
            self.scene_dirty = True
            self.scene_dirty_reason = "tile_paint"
            self.scene_dirty_counter = 1
            self._reload_called = 0

        def reload_scene_from_disk(self) -> bool:
            self._reload_called += 1
            self.scene_dirty = False
            self.scene_dirty_reason = ""
            return True

    window = _Window()
    controller = type("C", (), {"window": window})()

    assert input_capture.handle_key_press(controller, arcade.key.R, arcade.key.MOD_CTRL) is True
    assert window._reload_called == 1
    assert window.scene_dirty is False
    assert capsys.readouterr().out.strip() == "SCENE_RELOAD ok"

