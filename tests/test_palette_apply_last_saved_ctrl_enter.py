from __future__ import annotations

from pathlib import Path

import arcade

from engine.paths import get_content_roots, set_content_roots


def test_palette_apply_last_saved_ctrl_enter(monkeypatch, tmp_path: Path) -> None:
    from engine.input_runtime.capture import handle_key_press
    from engine.palette_mode import get_state
    from engine.tooling_runtime.capture_persist import persist_capture_payload

    original_roots = get_content_roots()
    set_content_roots([tmp_path])
    try:
        out_dir = tmp_path / "packs" / "p"
        monkeypatch.setenv("MESH_CAPTURE_OUT_DIR", str(out_dir))

        result = persist_capture_payload("brush", {"id": "capture_brush_1x1", "w": 1, "h": 1, "mask_tile": -1, "tiles": [[9]]})
        assert result.ok is True
        assert result.rel_path == "packs/p/brushes/capture_brush_1x1.json"

        state = get_state()
        state.reset()
        state.enabled = True
        state.mode = "BRUSHES"
        state.stamps = []
        state.brushes = []
        state.hot_add_item(rel_path=result.rel_path)

        scene_payload = {
            "tilemap": {
                "width": 4,
                "height": 3,
                "tile_layers": [{"id": "ground", "tiles": [0] * (4 * 3)}],
            },
            "entities": [],
        }

        class _Window:
            show_debug = True
            console_controller = type("C", (), {"active": False, "toggle": lambda *_a: None, "process_key": lambda *_a: False})()
            ui_controller = type("U", (), {"on_key_press": lambda *_a: False})()
            editor_controller = type("E", (), {"active": False})()

            camera_controller = type("Cam", (), {"camera_x": 0, "camera_y": 0})()
            input_controller = type("In", (), {"mouse_x": 32, "mouse_y": 32})()
            scene_controller = type("S", (), {"current_scene_data": scene_payload, "request_scene_reload": lambda *_a: None})()

        controller = type("Ctl", (), {"window": _Window(), "manager": type("M", (), {"press": lambda *_a: None})(), "_keys": set()})()

        assert handle_key_press(controller, arcade.key.ENTER, arcade.key.MOD_CTRL) is True
        tiles = scene_payload["tilemap"]["tile_layers"][0]["tiles"]
        assert tiles[1 + 1 * 4] == 9
    finally:
        set_content_roots(original_roots)

