from __future__ import annotations

from unittest.mock import MagicMock

import pytest


pytestmark = [pytest.mark.integration, pytest.mark.slow]

from engine.constants import EVENT_ENTERED_ZONE
from engine.game_state_controller import GameStateController
from engine.scene_index import SceneIndex
from engine.scene_controller import SceneController
from engine import savegame
from tests._typing import as_any


class _WindowForGameState:
    def __init__(self):
        self.engine_config = MagicMock()


def test_entered_zone_event_records_last_zone_id():
    window = _WindowForGameState()
    controller = GameStateController(as_any(window))

    controller.handle_event({"type": EVENT_ENTERED_ZONE, "payload": {"zone": "ZoneA"}})

    assert controller.get_var("last_zone_id") == "ZoneA"


def test_snapshot_payload_includes_spawn_zone_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    class _StubSceneController:
        def __init__(self, scene_path: str) -> None:
            self.current_scene_path = scene_path

    class _StubEngineConfig:
        def __init__(self, world_file: str | None) -> None:
            self.world_file = world_file

    class _StubWindow:
        def __init__(self) -> None:
            self.engine_config = _StubEngineConfig("worlds/act1_prologue.json")
            self.scene_controller = _StubSceneController("packs/core_regions/scenes/Act1_Prologue_Cabin.json")
            self.game_state_controller = GameStateController(as_any(self))
            self.set_next_spawn_point = MagicMock()
            self.request_scene_change = MagicMock()

    window = _StubWindow()

    window.game_state_controller.handle_event({"type": EVENT_ENTERED_ZONE, "payload": {"zone": "ZoneA"}})

    payload = savegame.dump_snapshot(window.game_state_controller)
    assert payload["spawn_zone_id"] == "ZoneA"


def test_snapshot_load_queues_spawn_zone_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    class _StubSceneController:
        def __init__(self, scene_path: str) -> None:
            self.current_scene_path = scene_path

    class _StubEngineConfig:
        def __init__(self, world_file: str | None) -> None:
            self.world_file = world_file

    class _StubWindow:
        def __init__(self) -> None:
            self.engine_config = _StubEngineConfig("worlds/act1_prologue.json")
            self.scene_controller = _StubSceneController("packs/core_regions/scenes/Act1_Prologue_Cabin.json")
            self.game_state_controller = GameStateController(as_any(self))
            self.set_next_spawn_point = MagicMock()
            self.request_scene_change = MagicMock()

    window = _StubWindow()
    window.game_state_controller.set_var("last_zone_id", "ZoneA")

    path = savegame.QUICK_SNAPSHOT_PATH
    assert savegame.save_quick_snapshot(window, path=path) is True

    # Reset, then load; should queue spawn anchor.
    window.set_next_spawn_point.reset_mock()
    assert savegame.load_quick_snapshot(window, path=path) is True

    window.set_next_spawn_point.assert_called_once_with("ZoneA")


class _StubWindowForSceneController:
    def __init__(self, spawn_id: str | None):
        from engine.config import EngineConfig
        from engine.events import MeshEventBus

        cfg = EngineConfig()
        self.width = cfg.width
        self.height = cfg.height
        self.world_width = 2000
        self.world_height = 2000

        self.event_bus = MeshEventBus()
        self.scene_loader = MagicMock()
        self.assets = MagicMock()
        self.audio = MagicMock()
        self.camera_controller = MagicMock()
        self.camera_controller.zoom_state = MagicMock(current=1.0, target=1.0, speed=0.0, min_zoom=0.1, max_zoom=4.0)
        self.camera_controller.get_camera_center.return_value = (0.0, 0.0)
        self.tilemap_manager = MagicMock()
        self.show_debug = False
        self.console_controller = MagicMock()
        self.console_controller._format_param_value = lambda v: v
        self.console_log = MagicMock()

        self.day_night = None
        self._next_spawn_point = spawn_id

    def get_next_spawn_point(self):
        return self._next_spawn_point

    def _consume_next_spawn_point(self):
        self._next_spawn_point = None
        return None

    def clear_input_locks(self):
        pass


def test_pending_spawn_point_can_target_named_zone_entity():
    window = _StubWindowForSceneController("ZoneA")
    controller = SceneController(as_any(window))

    player = MagicMock()
    player.mesh_tag = "player"
    player.mesh_entity_data = {}

    zone = MagicMock()
    # Ensure we hit the SceneIndex id lookup path, not the legacy mesh_name scan.
    zone.mesh_name = "NotZoneA"
    zone.center_x = 123.0
    zone.center_y = 456.0
    zone.mesh_entity_data = {"id": "ZoneA"}

    controller._loaded_scene_data = {"spawns": {}}
    controller.layers["entities"] = [player, zone]
    controller._scene_index = SceneIndex.build_from_sprites([player, zone])

    controller._apply_pending_spawn_point()

    assert player.center_x == pytest.approx(123.0)
    assert player.center_y == pytest.approx(456.0)
