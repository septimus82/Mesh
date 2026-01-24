from __future__ import annotations

import arcade


def _world_for_tile(*, tx: int, ty: int, map_h: int, tile_w: int, tile_h: int) -> tuple[float, float]:
    row_from_bottom = int(map_h - 1 - int(ty))
    return ((float(tx) + 0.1) * float(tile_w), (float(row_from_bottom) + 0.1) * float(tile_h))


def test_tile_recent_updates_on_stroke_and_eyedropper(capsys) -> None:
    from engine.input_runtime import capture as input_capture
    from engine.palette_mode import get_state
    from engine.tile_paint_mode import TilePaintState

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False
    try:
        class _Instance:
            map_size = (2, 2)
            tile_size = (10, 10)

        class _SceneController:
            tilemap_instance = _Instance()

            def __init__(self) -> None:
                self._loaded_scene_source_data = {"tilemap": {"tile_layers": [{"id": "Ground", "tiles": [0, 0, 0, 0]}]}}
                self._loaded_scene_data = dict(self._loaded_scene_source_data)

            def _debug_iter_authoring_payloads(self) -> list[dict]:
                return [self._loaded_scene_source_data]

            def refresh_tilemap_layers(self) -> bool:  # pragma: no cover
                return True

        class _Window:
            show_debug = True
            tile_paint_state = TilePaintState(enabled=True, layer_id="Ground", tile_id=7)
            entity_paint_state = type("EP", (), {"enabled": False})()
            capture_state = type("CS", (), {"enabled": False})()
            scene_controller = _SceneController()
            editor_controller = type("E", (), {"active": False})()
            ui_controller = type("U", (), {"on_key_press": lambda *_a: False, "input_blocked": False})()
            console_controller = type("C", (), {"active": False, "toggle": lambda *_a: None})()

            @staticmethod
            def screen_to_world(x: float, y: float) -> tuple[float, float]:
                return (float(x), float(y))

        window = _Window()
        controller = type("Ctl", (), {"window": window, "manager": type("M", (), {"press": lambda *_a: None})(), "_keys": set()})()

        # Stroke (paint) updates recent with tile_id=7.
        x0, y0 = _world_for_tile(tx=0, ty=1, map_h=2, tile_w=10, tile_h=10)
        assert input_capture.handle_mouse_press(controller, x0, y0, arcade.MOUSE_BUTTON_LEFT, 0) is True
        assert input_capture.handle_mouse_release(controller, x0, y0, arcade.MOUSE_BUTTON_LEFT, 0) is True
        capsys.readouterr()
        assert getattr(window, "tile_recent", []) == [7]

        # Place a different tile and pick it (Shift+LMB).
        window.scene_controller._loaded_scene_source_data["tilemap"]["tile_layers"][0]["tiles"][0] = 42
        x1, y1 = _world_for_tile(tx=0, ty=0, map_h=2, tile_w=10, tile_h=10)
        assert input_capture.handle_mouse_press(controller, x1, y1, arcade.MOUSE_BUTTON_LEFT, arcade.key.MOD_SHIFT) is True
        capsys.readouterr()
        assert window.tile_paint_state.tile_id == 42
        assert getattr(window, "tile_recent", []) == [42, 7]
    finally:
        palette.enabled = original_enabled

