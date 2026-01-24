from __future__ import annotations

import arcade


class _Editor:
    active = False


class _Instance:
    map_size = (4, 3)
    tile_size = (16, 16)


class _SceneController:
    tilemap_instance = _Instance()

    def __init__(self) -> None:
        self._loaded_scene_data = {
            "tilemap": {
                "tile_layers": [{"id": "Ground", "tiles": [0] * (4 * 3)}],
            }
        }

    def refresh_tilemap_layers(self) -> bool:  # pragma: no cover
        return True


def test_tile_paint_mode_consumes_mouse_press_when_enabled() -> None:
    from engine.input_runtime import capture as input_capture
    from engine.tile_paint_mode import TilePaintState

    class _Window:
        editor_controller = _Editor()
        show_debug = True
        tile_paint_state = TilePaintState(enabled=True, layer_id="Ground", tile_id=7)
        scene_controller = _SceneController()

        @staticmethod
        def screen_to_world(x: float, y: float) -> tuple[float, float]:
            return (x, y)

    controller = type("C", (), {"window": _Window()})()
    assert input_capture.handle_mouse_press(controller, 1.0, 1.0, arcade.MOUSE_BUTTON_LEFT, 0) is True


def test_tile_paint_mode_does_not_consume_mouse_press_when_disabled() -> None:
    from engine.input_runtime import capture as input_capture
    from engine.tile_paint_mode import TilePaintState

    class _Window:
        editor_controller = _Editor()
        show_debug = True
        tile_paint_state = TilePaintState(enabled=False, layer_id="Ground", tile_id=7)
        scene_controller = _SceneController()

        @staticmethod
        def screen_to_world(x: float, y: float) -> tuple[float, float]:
            return (x, y)

    controller = type("C", (), {"window": _Window()})()
    assert input_capture.handle_mouse_press(controller, 1.0, 1.0, arcade.MOUSE_BUTTON_LEFT, 0) is False

