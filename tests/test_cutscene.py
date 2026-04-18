import json
from pathlib import Path

import engine.optional_arcade as optional_arcade
import pytest

from engine.cutscene_controller import CutsceneController
from engine.events import MeshEventBus
from engine.schema_validation import SchemaValidationError


pytestmark = [pytest.mark.fast]


class DummyCamera:
    def __init__(self):
        self.position = (0.0, 0.0)

    def move_to(self, pos):
        self.position = pos


class DummyCameraController:
    def __init__(self):
        self.camera = DummyCamera()

    def get_camera_center(self):
        return self.camera.position


class DummySceneController:
    def __init__(self, sprite):
        self._sprite = sprite
        self.all_sprites = [sprite]

    def find_sprite(self, identifier):
        name = str(identifier)
        if getattr(self._sprite, "mesh_name", None) == name:
            return self._sprite
        return None


class DummyGameState:
    def __init__(self):
        self.flags = {}
        self.counters = {}

    def set_flag(self, name, value=True):
        self.flags[name] = bool(value)

    def add_counter(self, name, delta):
        self.counters[name] = self.counters.get(name, 0) + delta


class DummyUIController:
    def __init__(self):
        self.active = False

    def show_dialogue(self, entries, *, owner: str):
        if entries:
            self.active = True
            return True
        return False

    def is_dialogue_active(self, *, owner: str | None = None):
        return self.active

    def clear(self):
        self.active = False


class DummyWindow:
    def __init__(self, sprite):
        self.scene_controller = DummySceneController(sprite)
        self.camera_controller = DummyCameraController()
        self.game_state_controller = DummyGameState()
        self.event_bus = MeshEventBus()
        self.ui_controller = DummyUIController()


class DialogueRunnerBehaviour:
    def __init__(self, dialogue_id: str):
        self.dialogue_id = dialogue_id
        self.started_with = None

    def start(self, node_id: str | None = None):
        self.started_with = node_id
        return True


def test_cutscene_wait_and_move():
    sprite = optional_arcade.arcade.Sprite()
    sprite.mesh_name = "hero"
    sprite.center_x = 0
    sprite.center_y = 0
    window = DummyWindow(sprite)
    controller = CutsceneController(window)
    controller.register_cutscenes(
        [
            {
                "id": "intro",
                "steps": [
                    {"type": "wait", "duration": 0.1},
                    {"type": "move_entity", "entity": "hero", "x": 10, "y": 5, "duration": 0.2},
                ],
            }
        ]
    )
    assert controller.play_cutscene("intro")
    controller.update(0.05)
    assert controller.is_running
    controller.update(0.1)  # finish wait, start move
    controller.update(0.2)  # finish move
    assert not controller.is_running
    assert sprite.center_x == 10
    assert sprite.center_y == 5


def test_cutscene_flags_counters_events():
    sprite = optional_arcade.arcade.Sprite()
    sprite.mesh_name = "hero"
    window = DummyWindow(sprite)
    events = []

    def on_evt(evt):
        events.append(evt)

    window.event_bus.subscribe("boom", lambda e: on_evt("boom"))
    controller = CutsceneController(window)
    controller.register_cutscenes(
        [
            {
                "id": "state",
                "steps": [
                    {"type": "set_flag", "name": "door_open", "value": True},
                    {"type": "add_counter", "name": "coins", "delta": 3},
                    {"type": "emit_event", "event": "boom"},
                ],
            }
        ]
    )
    controller.play_cutscene("state")
    controller.update(0.01)  # set_flag
    controller.update(0.01)  # add_counter
    controller.update(0.01)  # emit_event
    assert window.game_state_controller.flags.get("door_open") is True
    assert window.game_state_controller.counters.get("coins") == 3
    assert "boom" in events


def test_cutscene_camera_steps():
    sprite = optional_arcade.arcade.Sprite()
    sprite.mesh_name = "hero"
    sprite.center_x = 5
    sprite.center_y = 6
    window = DummyWindow(sprite)
    controller = CutsceneController(window)
    controller.register_cutscenes(
        [
            {
                "id": "cam",
                "steps": [
                    {"type": "camera_focus", "entity": "hero"},
                    {"type": "camera_pan", "x": 20, "y": 30, "duration": 0.5},
                ],
            }
        ]
    )
    controller.play_cutscene("cam")
    controller.update(0.01)
    assert window.camera_controller.camera.position == (5, 6)
    controller.update(0.5)
    assert window.camera_controller.camera.position == (20, 30)


def test_cutscene_dialogue_steps():
    sprite = optional_arcade.arcade.Sprite()
    sprite.mesh_name = "hero"
    window = DummyWindow(sprite)
    controller = CutsceneController(window)
    controller.register_cutscenes(
        [
            {
                "id": "dlg",
                "steps": [
                    {"type": "start_dialogue", "speaker": "Narrator", "text": "Hello"},
                    {"type": "wait_dialogue_end"},
                ],
            }
        ]
    )
    controller.play_cutscene("dlg")
    controller.update(0.01)
    assert window.ui_controller.active
    # Complete dialogue
    window.ui_controller.clear()
    controller.update(0.01)
    assert not controller.is_running


def test_cutscene_start_dialogue_targets_dialogue_runner():
    sprite = optional_arcade.arcade.Sprite()
    sprite.mesh_name = "mentor"
    runner = DialogueRunnerBehaviour("intro_dialogue")
    sprite.behaviours = [runner]
    window = DummyWindow(sprite)
    window.ui_controller = None
    controller = CutsceneController(window)
    controller.register_cutscenes(
        [
            {
                "id": "intro",
                "steps": [
                    {
                        "type": "start_dialogue",
                        "dialogue_id": "intro_dialogue",
                        "target": "mentor",
                        "node_id": "start",
                    }
                ],
            }
        ]
    )

    assert controller.play_cutscene("intro")

    controller.update(0.01)

    assert runner.started_with == "start"


def test_load_from_file_registers_valid_cutscenes(tmp_path: Path):
    path = tmp_path / "cutscenes.json"
    path.write_text(
        json.dumps(
            {
                "cutscenes": [
                    {
                        "id": "intro",
                        "steps": [
                            {"type": "wait", "duration": 0.1},
                            {"type": "emit_event", "event": "done"},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    sprite = optional_arcade.arcade.Sprite()
    sprite.mesh_name = "hero"
    controller = CutsceneController(DummyWindow(sprite))

    controller.load_from_file(str(path))

    assert "intro" in controller.cutscenes


def test_load_from_file_invalid_json_raises(tmp_path: Path):
    path = tmp_path / "cutscenes.json"
    path.write_text("{bad json", encoding="utf-8")

    sprite = optional_arcade.arcade.Sprite()
    sprite.mesh_name = "hero"
    controller = CutsceneController(DummyWindow(sprite))

    with pytest.raises(json.JSONDecodeError):
        controller.load_from_file(str(path))


def test_load_from_file_schema_invalid_raises(tmp_path: Path):
    path = tmp_path / "cutscenes.json"
    path.write_text(
        json.dumps(
            {
                "cutscenes": [
                    {
                        "id": "intro",
                        "commands": [{"type": "wait", "duration": 0.1}],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    sprite = optional_arcade.arcade.Sprite()
    sprite.mesh_name = "hero"
    controller = CutsceneController(DummyWindow(sprite))

    with pytest.raises(SchemaValidationError):
        controller.load_from_file(str(path))
