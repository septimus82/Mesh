from __future__ import annotations

import arcade


def test_scene_dirty_marked_by_tile_paint_mouse_press() -> None:
    from engine.input_runtime import capture as input_capture
    from engine.tile_paint_mode import TilePaintState

    class _SceneController:
        def __init__(self) -> None:
            self.tilemap_instance = type("T", (), {"map_size": (2, 2), "tile_size": (32, 32)})()
            self._loaded_scene_data = {"tilemap": {"tile_layers": [{"id": "ground", "tiles": [0, 0, 0, 0]}]}}
            self._loaded_scene_source_data = {"tilemap": {"tile_layers": [{"id": "ground", "tiles": [0, 0, 0, 0]}]}}

        def _debug_iter_authoring_payloads(self):
            return [self._loaded_scene_data, self._loaded_scene_source_data]

        def refresh_tilemap_layers(self) -> bool:
            return True

    class _Window:
        show_debug = True
        tile_paint_state = TilePaintState(enabled=True, layer_id="ground", tile_id=5)
        scene_controller = _SceneController()
        editor_controller = type("E", (), {"active": False})()

        def __init__(self) -> None:
            self.scene_dirty = False
            self.scene_dirty_reason = ""
            self.scene_dirty_counter = 0

        def screen_to_world(self, x: float, y: float):
            return float(x), float(y)

        def mark_scene_dirty(self, reason: str) -> None:
            self.scene_dirty = True
            self.scene_dirty_reason = str(reason)
            self.scene_dirty_counter += 1

    window = _Window()
    controller = type("C", (), {"window": window})()

    assert input_capture.handle_mouse_press(controller, 16, 16, arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert input_capture.handle_mouse_release(controller, 16, 16, arcade.MOUSE_BUTTON_LEFT, 0) is True
    assert window.scene_dirty is True
    assert window.scene_dirty_reason == "tile_paint_drag"
    assert window.scene_dirty_counter == 1
    # world_to_tile uses y=0 as the top row; (16,16) hits tile (0,1) for a 2x2 map.
    assert window.scene_controller._loaded_scene_data["tilemap"]["tile_layers"][0]["tiles"][2] == 5
    assert window.scene_controller._loaded_scene_source_data["tilemap"]["tile_layers"][0]["tiles"][2] == 5
