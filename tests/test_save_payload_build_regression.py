from __future__ import annotations

import json
from unittest.mock import MagicMock

from engine import savegame
from engine.save_manager import SaveManager
from engine.save_runtime import payloads as save_payloads


class _SnapshotWindow:
    def __init__(self) -> None:
        self.engine_config = MagicMock(world_file="worlds/act1_prologue.json")
        self.world_controller = MagicMock(id="act1_prologue")
        self.scene_controller = MagicMock(current_scene_path="packs/core_regions/scenes/Act1_Prologue_Cabin.json")
        self.game_state_controller = MagicMock()
        self.game_state_controller.window = self
        self.game_state_controller.state = MagicMock(
            flags={"zzz": True, "aaa": True, "bbb": False},
            counters={"gold": 7},
            variables={"last_zone_id": " ZoneA "},
        )


def test_snapshot_builder_matches_dump_snapshot() -> None:
    window = _SnapshotWindow()
    built = save_payloads.build_snapshot_payload(window)
    dumped = savegame.dump_snapshot(window.game_state_controller)
    assert built == dumped


def test_slot_builder_matches_saved_file_bytes(tmp_path, monkeypatch) -> None:
    window = MagicMock()
    window.scene_controller = MagicMock()
    window.scene_controller.current_scene_path = "scenes/test.json"
    window.scene_controller.build_scene_snapshot.return_value = {"entities": [], "settings": {}}
    window.game_state_controller = MagicMock()
    window.game_state_controller.export_state.return_value = {"flags": {}, "counters": {"gold": 0}, "perks": []}
    window.game_state_controller.get_var.return_value = " ZoneA "
    window.player_hud = MagicMock()

    manager = SaveManager(window, save_dir=str(tmp_path))
    monkeypatch.setattr(manager, "_get_timestamp", lambda: "2000-01-01T00:00:00")

    assert manager.save_game("slot1") is True
    path = manager.get_save_path("slot1")
    on_disk = json.loads(path.read_text(encoding="utf-8"))

    built, _sig = save_payloads.build_slot_payload(window, "slot1", compact=False, timestamp="2000-01-01T00:00:00")
    assert on_disk == built

    assert on_disk.get("spawn_zone_id") == "ZoneA"
    assert path.read_bytes().endswith(b"\n")

