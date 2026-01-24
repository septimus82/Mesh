from __future__ import annotations

import arcade


class _Editor:
    active = False


def test_entity_paint_mode_consumes_mouse_press_when_enabled() -> None:
    from engine.entity_paint_mode import EntityPaintState, load_prefab_infos
    from engine.input_runtime import capture as input_capture

    class _SceneController:
        current_scene_path = "scenes/test.json"

        def __init__(self) -> None:
            self._loaded_scene_data = {"name": "Test", "entities": [], "tilemap": {"width": 1, "height": 1, "tilewidth": 16, "tileheight": 16}}
            self._loaded_scene_source_data = dict(self._loaded_scene_data)

        def get_authored_scene_payload(self):  # pragma: no cover
            return self._loaded_scene_source_data

        def debug_add_entity_payload(self, _payload):  # pragma: no cover
            return True

    class _Window:
        editor_controller = _Editor()
        show_debug = True
        entity_paint_state = EntityPaintState(enabled=True, prefabs=load_prefab_infos())
        scene_controller = _SceneController()

        @staticmethod
        def screen_to_world(x: float, y: float) -> tuple[float, float]:
            return (x, y)

    controller = type("C", (), {"window": _Window()})()
    assert input_capture.handle_mouse_press(controller, 1.0, 1.0, arcade.MOUSE_BUTTON_LEFT, 0) is True

