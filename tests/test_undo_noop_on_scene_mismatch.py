from __future__ import annotations

import copy

import arcade


class _FakeSceneController:
    def __init__(self, *, scene_path: str, payload: dict) -> None:
        self.current_scene_path = scene_path
        self._loaded_scene_source_data = copy.deepcopy(payload)
        self._loaded_scene_data = copy.deepcopy(payload)

    def get_authored_scene_payload(self) -> dict:
        return self._loaded_scene_source_data

    def debug_apply_authored_scene_payload(self, authored_payload: dict) -> bool:
        self._loaded_scene_source_data = copy.deepcopy(authored_payload)
        self._loaded_scene_data = copy.deepcopy(authored_payload)
        return True


def test_undo_noop_on_scene_mismatch(capsys) -> None:
    from engine.game import GameWindow
    from engine.input_runtime import capture as input_capture
    from engine.palette_mode import get_state

    palette = get_state()
    original_enabled = bool(palette.enabled)
    palette.enabled = False
    try:
        sc = _FakeSceneController(scene_path="scenes/a.json", payload={"entities": [{"id": "a"}]})
        window = type(
            "W",
            (),
            {
                "show_debug": True,
                "scene_controller": sc,
                "scene_dirty_counter": 0,
                "scene_dirty_reason": "",
                "scene_dirty": False,
                "undo_stack": [],
                "redo_stack": [],
                "_undo_ts_counter": 0,
                "_undo_suppress_count": 0,
                "editor_controller": type("E", (), {"active": False})(),
                "ui_controller": type("U", (), {"on_key_press": lambda *_a: False, "input_blocked": False})(),
                "console_controller": type("C", (), {"active": False, "toggle": lambda *_a: None})(),
            },
        )()

        window.push_undo_frame = lambda reason: GameWindow.push_undo_frame(window, reason)  # type: ignore[attr-defined]
        window.undo = lambda: GameWindow.undo(window)  # type: ignore[attr-defined]

        assert window.push_undo_frame("test") is True
        assert len(window.undo_stack) == 1

        sc.current_scene_path = "scenes/b.json"
        controller = type("Ctl", (), {"window": window, "manager": type("M", (), {"press": lambda *_a: None})(), "_keys": set()})()
        assert input_capture.handle_key_press(controller, arcade.key.Z, arcade.key.MOD_CTRL) is True
        assert capsys.readouterr().out.strip() == "UNDO noop reason=scene_mismatch"
        assert len(window.undo_stack) == 1
    finally:
        palette.enabled = original_enabled
