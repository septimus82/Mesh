from __future__ import annotations

import pytest

import engine.optional_arcade as optional_arcade


def test_authoring_copy_coords_hotkey_player_pos(capsys) -> None:
    from engine.input_runtime import capture as input_capture

    class _Console:
        active = False

    class _UI:
        def on_key_press(self, _key: int, _mod: int) -> bool:
            return False

    def _provider(_window):
        return {"player": {"x": 12.25, "y": 99.75}, "hover": None}

    class _Overlay:
        visible = False
        provider = staticmethod(_provider)

    class _Window:
        console_controller = _Console()
        ui_controller = _UI()
        show_debug = True
        scene_inspector_overlay = _Overlay()

    controller = type("C", (), {"window": _Window()})()

    assert input_capture.handle_key_press(controller, optional_arcade.arcade.key.F9, 0) is True
    assert capsys.readouterr().out.strip() == "PLAYER_POS --x 12.2 --y 99.8"


def test_authoring_copy_coords_hotkey_hover_pos_shift_f9(capsys) -> None:
    from engine.input_runtime import capture as input_capture

    class _Console:
        active = False

    class _UI:
        def on_key_press(self, _key: int, _mod: int) -> bool:
            return False

    def _provider(_window):
        return {
            "player": {"x": 0, "y": 0},
            "hover": {"id": "e123", "prefab_id": "slime_blob", "pos": {"x": 10.0, "y": 20.0}},
        }

    class _Overlay:
        visible = True
        provider = staticmethod(_provider)

    class _Window:
        console_controller = _Console()
        ui_controller = _UI()
        show_debug = False
        scene_inspector_overlay = _Overlay()

    controller = type("C", (), {"window": _Window()})()

    assert input_capture.handle_key_press(controller, optional_arcade.arcade.key.F9, optional_arcade.arcade.key.MOD_SHIFT) is True
    assert capsys.readouterr().out.strip() == "HOVER_POS --x 10 --y 20 --id e123 --prefab slime_blob"


def test_authoring_copy_coords_hotkey_hover_pos_missing_entity(capsys) -> None:
    from engine.input_runtime import capture as input_capture

    class _Console:
        active = False

    class _UI:
        def on_key_press(self, _key: int, _mod: int) -> bool:
            return False

    def _provider(_window):
        return {"player": {"x": 0, "y": 0}}

    class _Overlay:
        visible = True
        provider = staticmethod(_provider)

    class _Window:
        console_controller = _Console()
        ui_controller = _UI()
        show_debug = True
        scene_inspector_overlay = _Overlay()

    controller = type("C", (), {"window": _Window()})()

    assert input_capture.handle_key_press(controller, optional_arcade.arcade.key.F9, optional_arcade.arcade.key.MOD_SHIFT) is True
    assert capsys.readouterr().out.strip() == "HOVER_POS (no hovered entity)"


@pytest.mark.fast
def test_f9_quick_loads_when_debug_off(capsys) -> None:
    from engine.input_runtime import capture as input_capture

    class _Console:
        active = False

    class _UI:
        def on_key_press(self, _key: int, _mod: int) -> bool:
            return False

    class _Overlay:
        visible = False
        provider = None

    class _Window:
        console_controller = _Console()
        ui_controller = _UI()
        show_debug = False
        scene_inspector_overlay = _Overlay()

        def __init__(self) -> None:
            self._logs: list[str] = []
            self._paused = False

        def _toggle_paused_state(self) -> bool:
            self._paused = not self._paused
            return self._paused

        def console_log(self, message: str) -> None:
            self._logs.append(str(message))

    class _SaveManager:
        def __init__(self) -> None:
            self.loaded: list[str] = []

        def load_game(self, slot: str) -> bool:
            self.loaded.append(slot)
            return True

    window = _Window()
    window.save_manager = _SaveManager()
    controller = type("C", (), {"window": window})()

    assert input_capture.handle_key_press(controller, optional_arcade.arcade.key.F9, 0) is True
    assert capsys.readouterr().out.strip() == ""  # no coordinates copied outside debugging
    assert window.save_manager.loaded == ["quicksave"]  # F5 saves this slot, F9 loads it
    assert window._paused is False

