import arcade

from engine.config import EngineConfig
from engine.editor_controller import EditorModeController


class DummySceneController:
    def __init__(self):
        self._loaded_scene_data = {"lights": []}


class DummyWindow:
    def __init__(self):
        cfg = EngineConfig()
        self.width = cfg.width
        self.height = cfg.height
        self._mouse_x = 0
        self._mouse_y = 0
        self.scene_controller = DummySceneController()

    def screen_to_world(self, x, y):
        return float(x), float(y)


def make_controller():
    window = DummyWindow()
    controller = EditorModeController(window)
    controller.active = True
    controller._toggle_lights_mode(True)
    return controller, window


def test_add_light_command():
    controller, window = make_controller()
    controller._add_light(10, 20)
    lights = window.scene_controller._loaded_scene_data["lights"]
    assert len(lights) == 1
    assert controller.scene_dirty


def test_move_light_command_and_undo():
    controller, window = make_controller()
    controller._add_light(10, 20)
    controller.lights_selection = 0
    lights = window.scene_controller._loaded_scene_data["lights"]
    lights[0]["x"] = 30
    lights[0]["y"] = 40
    controller._push_command({
        "type": "MoveLight",
        "index": 0,
        "from": (10.0, 20.0),
        "to": (30.0, 40.0),
    })
    controller.undo_last()
    assert lights[0]["x"] == 10.0 and lights[0]["y"] == 20.0
    controller.redo_last()
    assert lights[0]["x"] == 30.0 and lights[0]["y"] == 40.0


def test_edit_light_command():
    controller, window = make_controller()
    controller._add_light(10, 20)
    controller.lights_selection = 0
    controller._handle_lights_key_input(arcade.key.RIGHT, 0)
    lights = window.scene_controller._loaded_scene_data["lights"]
    assert lights[0]["radius"] > 160.0


def test_delete_light_command():
    controller, window = make_controller()
    controller._add_light(10, 20)
    controller.lights_selection = 0
    controller._delete_selected_light()
    lights = window.scene_controller._loaded_scene_data["lights"]
    assert lights == []
    controller.undo_last()
    assert len(lights) == 1
