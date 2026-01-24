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
        self.tilemap_instance = _TilemapInstance()

    def _debug_iter_authoring_payloads(self) -> list[dict]:
        return [self._loaded_scene_source_data]

    def get_authored_scene_payload(self) -> dict:
        return self._loaded_scene_source_data

    def debug_apply_authored_scene_payload(self, authored_payload: dict) -> bool:
        self._loaded_scene_source_data = copy.deepcopy(authored_payload)
        return True


def test_tile_paint_stroke_deterministic_apply_order(monkeypatch) -> None:
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

        window.mark_scene_dirty = lambda *_a: None  # type: ignore[attr-defined]
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

        calls: list[tuple[int, int]] = []

        import engine.tile_paint_mode as tpm

        original_set_tile = tpm.set_tile

        def _set_tile(tiles, *, dims, x, y, tile):
            calls.append((int(x), int(y)))
            return original_set_tile(tiles, dims=dims, x=x, y=y, tile=tile)

        monkeypatch.setattr(tpm, "set_tile", _set_tile)

        # Visit coords in a non-sorted order; the apply order should still be y,x sorted.
        start = (3, 3)
        visited = [(4, 0), (0, 4), (2, 1), (1, 1)]

        x0, y0 = _world_for_tile(tx=start[0], ty=start[1], map_h=5, tile_w=10, tile_h=10)
        assert input_capture.handle_mouse_press(controller, x0, y0, arcade.MOUSE_BUTTON_LEFT, 0) is True
        for tx, ty in visited:
            x, y = _world_for_tile(tx=tx, ty=ty, map_h=5, tile_w=10, tile_h=10)
            input_capture.handle_mouse_drag(controller, x, y, 0, 0, arcade.MOUSE_BUTTON_LEFT, 0)
        assert input_capture.handle_mouse_release(controller, x0, y0, arcade.MOUSE_BUTTON_LEFT, 0) is True

        expected_coords = {(start[0], start[1]), *visited}
        expected_order = sorted(expected_coords, key=lambda p: (p[1], p[0]))
        assert calls == expected_order
    finally:
        palette.enabled = original_enabled

