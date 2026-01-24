from __future__ import annotations

import copy

import arcade


def _world_for_tile(*, tx: int, ty: int, map_h: int, tile_w: int, tile_h: int) -> tuple[float, float]:
    row_from_bottom = int(map_h - 1 - int(ty))
    return ((float(tx) + 0.1) * float(tile_w), (float(row_from_bottom) + 0.1) * float(tile_h))


class _TilemapInstance:
    map_size = (5, 5)
    tile_size = (10, 10)


class _FakeSceneController:
    def __init__(self, *, scene_path: str, authored: dict) -> None:
        self.current_scene_path = scene_path
        self._loaded_scene_source_data = copy.deepcopy(authored)
        self._loaded_scene_data = copy.deepcopy(authored)
        self.tilemap_instance = _TilemapInstance()

    def _debug_iter_authoring_payloads(self) -> list[dict]:
        return [self._loaded_scene_source_data]

    def get_authored_scene_payload(self) -> dict:
        return self._loaded_scene_source_data

    def debug_apply_authored_scene_payload(self, authored_payload: dict) -> bool:
        self._loaded_scene_source_data = copy.deepcopy(authored_payload)
        self._loaded_scene_data = copy.deepcopy(authored_payload)
        return True

    def refresh_tilemap_layers(self) -> bool:  # pragma: no cover
        return True


def _get_tiles(scene_payload: dict) -> list[int]:
    tilemap = scene_payload.get("tilemap")
    assert isinstance(tilemap, dict)
    layers = tilemap.get("tile_layers")
    assert isinstance(layers, list)
    layer = next((e for e in layers if isinstance(e, dict) and e.get("id") == "Ground"), None)
    assert isinstance(layer, dict)
    tiles = layer.get("tiles")
    assert isinstance(tiles, list)
    return tiles


def test_tile_paint_drag_single_undo_frame() -> None:
    from engine.game import GameWindow
    from engine.input_runtime import capture as input_capture
    from engine.palette_mode import get_state
    from engine.tile_paint_mode import TilePaintState

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False
    try:
        authored = {
            "tilemap": {
                "width": 5,
                "height": 5,
                "tilewidth": 10,
                "tileheight": 10,
                "tile_layers": [{"id": "Ground", "z": 0, "tiles": [0] * (5 * 5)}],
            }
        }
        sc = _FakeSceneController(scene_path="scenes/foo.json", authored=authored)

        window = type(
            "W",
            (),
            {
                "show_debug": True,
                "scene_controller": sc,
                "tile_paint_state": TilePaintState(enabled=True, layer_id="Ground", tile_id=7),
                "scene_dirty": False,
                "scene_dirty_reason": "",
                "scene_dirty_counter": 0,
                "undo_stack": [],
                "redo_stack": [],
                "_undo_ts_counter": 0,
                "_undo_suppress_count": 0,
                "editor_controller": type("E", (), {"active": False})(),
                "ui_controller": type("U", (), {"on_key_press": lambda *_a: False, "input_blocked": False})(),
                "console_controller": type("C", (), {"active": False, "toggle": lambda *_a: None})(),
                "screen_to_world": staticmethod(lambda x, y: (float(x), float(y))),
            },
        )()

        def _mark_scene_dirty(self, reason: str) -> None:
            self.scene_dirty = True
            self.scene_dirty_reason = str(reason)
            self.scene_dirty_counter += 1

        window.mark_scene_dirty = _mark_scene_dirty.__get__(window)  # type: ignore[attr-defined]
        window.push_undo_frame = lambda reason: GameWindow.push_undo_frame(window, reason)  # type: ignore[attr-defined]

        controller = type(
            "Ctl",
            (),
            {
                "window": window,
                "manager": type("M", (), {"press": lambda *_a: None})(),
                "_keys": set(),
            },
        )()

        # Drag-paint 3 tiles.
        x0, y0 = _world_for_tile(tx=1, ty=1, map_h=5, tile_w=10, tile_h=10)
        assert input_capture.handle_mouse_press(controller, x0, y0, arcade.MOUSE_BUTTON_LEFT, 0) is True
        for tx, ty in [(3, 1), (0, 4)]:
            x, y = _world_for_tile(tx=tx, ty=ty, map_h=5, tile_w=10, tile_h=10)
            input_capture.handle_mouse_drag(controller, x, y, 0, 0, arcade.MOUSE_BUTTON_LEFT, 0)
        assert input_capture.handle_mouse_release(controller, x0, y0, arcade.MOUSE_BUTTON_LEFT, 0) is True

        tiles = _get_tiles(sc.get_authored_scene_payload())
        for tx, ty in {(1, 1), (3, 1), (0, 4)}:
            assert tiles[ty * 5 + tx] == 7

        assert len(window.undo_stack) == 1
        assert window.scene_dirty is True
        assert window.scene_dirty_reason == "tile_paint_drag"
        assert window.scene_dirty_counter == 1
    finally:
        palette.enabled = original_enabled

