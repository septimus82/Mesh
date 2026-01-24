from __future__ import annotations

import arcade


def test_format_scene_inspector_text_is_stable() -> None:
    from engine.ui import format_scene_inspector_text

    payload = {
        "scene_path": "scenes/door_interior.json",
        "player": {"x": 12.25, "y": 99.75},
        "hover": {"id": "e123", "prefab_id": "slime_blob", "mesh_name": "Slime", "pos": {"x": 10, "y": 20}},
        "flags": {"total": 7, "on": 2, "keys": ["quest:started", "switch:door_open"]},
    }

    text = format_scene_inspector_text(payload)
    assert "Scene Inspector (F10)" in text
    assert "scene: scenes/door_interior.json" in text
    assert "player: 12.2,99.8" in text
    assert "hover: id=e123 prefab=slime_blob name=Slime pos=10.0,20.0" in text
    assert "flags: on=2/7 keys=quest:started, switch:door_open" in text


def test_scene_inspector_overlay_toggle_key() -> None:
    from engine.input_runtime import capture as input_capture

    class _Console:
        active = False

    class _UI:
        def on_key_press(self, _key: int, _mod: int) -> bool:
            return False

    class _Overlay:
        visible = False

        def toggle(self) -> bool:
            self.visible = not self.visible
            return self.visible

    overlay = _Overlay()

    class _Window:
        console_controller = _Console()
        ui_controller = _UI()
        scene_inspector_overlay = overlay

    controller = type("C", (), {"window": _Window()})()

    assert input_capture.handle_key_press(controller, arcade.key.F10, 0) is True
    assert overlay.visible is True
    assert input_capture.handle_key_press(controller, arcade.key.F10, 0) is True
    assert overlay.visible is False

