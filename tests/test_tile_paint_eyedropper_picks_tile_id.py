from __future__ import annotations

import arcade


def _world_for_tile(*, tx: int, ty: int, map_h: int, tile_w: int, tile_h: int) -> tuple[float, float]:
    row_from_bottom = int(map_h - 1 - int(ty))
    return ((float(tx) + 0.1) * float(tile_w), (float(row_from_bottom) + 0.1) * float(tile_h))


def test_tile_paint_eyedropper_picks_tile_id(capsys) -> None:
    from engine.input_runtime import capture as input_capture
    from engine.palette_mode import get_state
    from engine.tile_paint_mode import TilePaintState

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False
    try:
        class _Instance:
            map_size = (5, 5)
            tile_size = (10, 10)

        class _SceneController:
            tilemap_instance = _Instance()

            def __init__(self) -> None:
                tiles = [0] * (5 * 5)
                tiles[3 * 5 + 2] = 42
                self._loaded_scene_source_data = {"tilemap": {"tile_layers": [{"id": "Ground", "tiles": tiles}]}}

            def _debug_iter_authoring_payloads(self) -> list[dict]:
                return [self._loaded_scene_source_data]

        class _Window:
            show_debug = True
            editor_controller = type("E", (), {"active": False})()
            scene_controller = _SceneController()
            tile_paint_state = TilePaintState(enabled=True, layer_id="Ground", tile_id=7)

            @staticmethod
            def screen_to_world(x: float, y: float) -> tuple[float, float]:
                return (float(x), float(y))

        window = _Window()
        controller = type("C", (), {"window": window})()

        x, y = _world_for_tile(tx=2, ty=3, map_h=5, tile_w=10, tile_h=10)
        assert input_capture.handle_mouse_press(controller, x, y, arcade.MOUSE_BUTTON_LEFT, arcade.key.MOD_SHIFT) is True
        assert window.tile_paint_state.tile_id == 42
        assert capsys.readouterr().out.strip() == "TILE_PICK ok tile=42 layer=Ground"
    finally:
        palette.enabled = original_enabled

