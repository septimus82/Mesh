import types
from unittest.mock import MagicMock

import arcade
import pytest

from engine.behaviours.scene_exit import SceneExit
from engine.events import MeshEventBus
from engine.scene_controller import SceneController


pytestmark = [pytest.mark.integration, pytest.mark.slow]


class StubWindow:
    def __init__(self):
        from engine.config import EngineConfig
        cfg = EngineConfig()
        self.width = cfg.width
        self.height = cfg.height
        self.world_width = 2000
        self.world_height = 2000
        self.event_bus = MeshEventBus()
        self.game_state_controller = MagicMock()

        # Minimal stubs used by SceneController internals
        self.scene_loader = MagicMock()
        self.assets = MagicMock()
        self.audio = MagicMock()
        self.camera_controller = MagicMock()
        self.camera_controller.zoom_state = MagicMock(
            current=1.0, target=1.0, speed=0.0, min_zoom=0.1, max_zoom=4.0
        )
        self.camera_controller.get_camera_center.return_value = (0.0, 0.0)
        self.tilemap_manager = MagicMock()
        self.show_debug = False
        self.console_controller = MagicMock()
        self.console_controller._format_param_value = lambda v: v
        self.console_log = MagicMock()

        # Required by save/load paths
        self.day_night = None
        self.assets.clear = MagicMock()
        self.audio.clear_cache = MagicMock()
        self._event_queue = []

    def set_next_spawn_point(self, value):
        pass

    def _consume_next_spawn_point(self):
        return None


def test_scene_exit_queues_scene_change():
    window = StubWindow()
    window.scene_controller = MagicMock()
    entity = MagicMock()

    behaviour = SceneExit(
        entity,
        window,
        listen_event="door_open",
        target_scene="scenes/forest.json",
        target_spawn="from_village",
    )

    window.event_bus.emit("door_open")
    window.scene_controller.queue_scene_change.assert_called_once_with(
        "scenes/forest.json", "from_village"
    )

    behaviour.on_destroy()


def test_scene_controller_apply_spawn_places_player():
    window = StubWindow()
    controller = SceneController(window)
    controller._loaded_scene_data = {
        "spawns": {"default": {"x": 10, "y": 20}},
    }
    player = MagicMock()
    player.mesh_tag = "player"
    player.mesh_entity_data = {}
    controller.layers["entities"] = [player]

    controller.apply_spawn("default")

    assert player.center_x == pytest.approx(10.0)
    assert player.center_y == pytest.approx(20.0)


def test_scene_controller_perform_scene_change_updates_game_state():
    window = StubWindow()
    controller = SceneController(window)

    # Stub load_scene to avoid file IO
    def fake_load_scene(self, path):
        self._loaded_scene_data = {
            "spawns": {"default": {"x": 1, "y": 2}},
            "settings": {},
        }
        return self._loaded_scene_data

    controller.load_scene = types.MethodType(fake_load_scene, controller)

    player = MagicMock()
    player.mesh_tag = "player"
    player.mesh_entity_data = {}
    controller.layers["entities"] = [player]

    controller._perform_scene_change("scenes/cave.json", "default")

    window.game_state_controller.set_var.assert_any_call("last_scene_path", "scenes/cave.json")
    window.game_state_controller.set_var.assert_any_call("last_spawn_id", "default")
    assert player.center_x == pytest.approx(1.0)
    assert player.center_y == pytest.approx(2.0)
