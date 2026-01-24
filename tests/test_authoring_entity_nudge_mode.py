from __future__ import annotations

import engine.optional_arcade as optional_arcade


class _Manager:
    def __init__(self) -> None:
        self.pressed: list[int] = []

    def press(self, key: int) -> None:
        self.pressed.append(int(key))

    def release(self, key: int) -> None:  # pragma: no cover
        self.pressed.append(-int(key))


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

    def handle_input(self, _key: int, _mod: int) -> bool:  # pragma: no cover
        return False


def test_entity_nudge_selection_and_steps(capsys) -> None:
    from engine.input_runtime import capture as input_capture

    class _Sprite:
        def __init__(self) -> None:
            self.center_x = 100.0
            self.center_y = 200.0
            self.mesh_entity_data = {"id": "e1", "prefab_id": "slime_blob"}

    sprite = _Sprite()

    class _Scene:
        all_sprites = [sprite]

    def _provider(_window):
        return {"hover": {"id": "e1"}}

    class _Overlay:
        visible = True
        provider = staticmethod(_provider)

    class _Window:
        console_controller = _Console()
        ui_controller = _UI()
        editor_controller = _Editor()
        show_debug = False
        scene_inspector_overlay = _Overlay()
        scene_controller = _Scene()

        def __init__(self) -> None:
            self.authoring_selected_entity_id = None

        def console_log(self, _message: str) -> None:
            return

    window = _Window()
    controller = type(
        "C",
        (),
        {
            "window": window,
            "manager": _Manager(),
            "_keys": set(),
        },
    )()

    assert input_capture.handle_key_press(controller, optional_arcade.arcade.key.F12, 0) is True
    assert window.authoring_selected_entity_id == "e1"

    assert input_capture.handle_key_press(controller, optional_arcade.arcade.key.RIGHT, 0) is True
    assert sprite.center_x == 108.0
    assert sprite.center_y == 200.0

    assert input_capture.handle_key_press(controller, optional_arcade.arcade.key.UP, optional_arcade.arcade.key.MOD_SHIFT) is True
    assert sprite.center_x == 108.0
    assert sprite.center_y == 201.0

    assert input_capture.handle_key_press(controller, optional_arcade.arcade.key.LEFT, optional_arcade.arcade.key.MOD_CTRL) is True
    assert sprite.center_x == 76.0
    assert sprite.center_y == 201.0

    assert input_capture.handle_key_press(controller, optional_arcade.arcade.key.F9, optional_arcade.arcade.key.MOD_SHIFT) is True
    assert capsys.readouterr().out.strip() == "HOVER_POS --x 76 --y 201 --id e1 --prefab slime_blob"


def test_entity_nudge_debug_off_does_not_move_or_consume() -> None:
    from engine.input_runtime import capture as input_capture

    class _Sprite:
        def __init__(self) -> None:
            self.center_x = 10.0
            self.center_y = 20.0
            self.mesh_entity_data = {"id": "e1", "prefab_id": "slime_blob"}

    sprite = _Sprite()

    class _Scene:
        all_sprites = [sprite]

    class _Overlay:
        visible = False
        provider = None

    class _Window:
        console_controller = _Console()
        ui_controller = _UI()
        editor_controller = _Editor()
        show_debug = False
        scene_inspector_overlay = _Overlay()
        scene_controller = _Scene()
        authoring_selected_entity_id = "e1"

    manager = _Manager()
    controller = type("C", (), {"window": _Window(), "manager": manager, "_keys": set()})()

    assert input_capture.handle_key_press(controller, optional_arcade.arcade.key.RIGHT, 0) is False
    assert sprite.center_x == 10.0
    assert sprite.center_y == 20.0
    assert optional_arcade.arcade.key.RIGHT in manager.pressed
