from __future__ import annotations

import copy

import arcade

from tests._game_window_undo_stub import bind_game_window_undo_methods


class _TilemapInstance:
    map_size = (2, 2)
    tile_size = (16, 16)


class _FakeSceneController:
    def __init__(self, *, scene_path: str, authored: dict) -> None:
        self.current_scene_path = scene_path
        self._loaded_scene_source_data = copy.deepcopy(authored)
        self._loaded_scene_data = copy.deepcopy(authored)
        self.tilemap_instance = _TilemapInstance()

    def _debug_iter_authoring_payloads(self) -> list[dict]:
        return [self._loaded_scene_data, self._loaded_scene_source_data]

    def get_authored_scene_payload(self) -> dict:
        return self._loaded_scene_source_data

    def debug_apply_authored_scene_payload(self, authored_payload: dict) -> bool:
        self._loaded_scene_source_data = copy.deepcopy(authored_payload)
        self._loaded_scene_data = copy.deepcopy(authored_payload)
        return True


def _make_window(scene_controller: _FakeSceneController):
    from engine.tile_paint_mode import TilePaintState

    window = type(
        "W",
        (),
        {
            "show_debug": True,
            "scene_controller": scene_controller,
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

    bind_game_window_undo_methods(window, include_undo=True, include_redo=True)
    return window


def _get_ground_tiles(scene_payload: dict) -> list[int]:
    tilemap = scene_payload.get("tilemap")
    assert isinstance(tilemap, dict)
    layers = tilemap.get("tile_layers")
    assert isinstance(layers, list)
    layer = next((e for e in layers if isinstance(e, dict) and e.get("id") == "Ground"), None)
    assert isinstance(layer, dict)
    tiles = layer.get("tiles")
    assert isinstance(tiles, list)
    return tiles


def test_undo_redo_tile_paint_single_action(capsys) -> None:
    from engine.input_runtime import capture as input_capture
    from engine.palette_mode import get_state

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False
    try:
        authored = {
            "tilemap": {
                "width": 2,
                "height": 2,
                "tilewidth": 16,
                "tileheight": 16,
                "tile_layers": [{"id": "Ground", "z": 0, "tiles": [0, 0, 0, 0]}],
            }
        }
        sc = _FakeSceneController(scene_path="scenes/foo.json", authored=authored)
        window = _make_window(sc)
        controller = type(
            "Ctl",
            (),
            {
                "window": window,
                "manager": type("M", (), {"press": lambda *_a: None})(),
                "_keys": set(),
            },
        )()

        assert _get_ground_tiles(sc.get_authored_scene_payload()) == [0, 0, 0, 0]

        # Paint tile at world=(1,1) -> tile (0,1) in 2x2 map => idx 2.
        assert input_capture.handle_mouse_press(controller, 1.0, 1.0, arcade.MOUSE_BUTTON_LEFT, 0) is True
        assert input_capture.handle_mouse_release(controller, 1.0, 1.0, arcade.MOUSE_BUTTON_LEFT, 0) is True
        capsys.readouterr()
        assert _get_ground_tiles(sc.get_authored_scene_payload())[2] == 7
        assert len(window.undo_stack) == 1

        assert input_capture.handle_key_press(controller, arcade.key.Z, arcade.key.MOD_CTRL) is True
        assert capsys.readouterr().out.strip() == "UNDO ok depth=0 redo=1"
        assert _get_ground_tiles(sc.get_authored_scene_payload()) == [0, 0, 0, 0]

        assert input_capture.handle_key_press(controller, arcade.key.Y, arcade.key.MOD_CTRL) is True
        assert capsys.readouterr().out.strip() == "REDO ok depth=1 redo=0"
        assert _get_ground_tiles(sc.get_authored_scene_payload())[2] == 7
    finally:
        palette.enabled = original_enabled
