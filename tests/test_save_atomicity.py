import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from engine.save_manager import SaveManager
from engine import savegame


class _SaveManagerWindow:
    def __init__(self):
        self.scene_controller = MagicMock()
        self.scene_controller.current_scene_path = "scenes/test.json"
        self.scene_controller.build_scene_snapshot.return_value = {"entities": [], "settings": {}}
        self.game_state_controller = MagicMock()
        self.game_state_controller.export_state.return_value = {"flags": {}, "counters": {"gold": 0}, "perks": []}
        self.player_hud = MagicMock()


def test_save_manager_write_is_atomic_on_replace_failure(tmp_path, monkeypatch):
    window = _SaveManagerWindow()
    manager = SaveManager(window, save_dir=str(tmp_path))

    path = tmp_path / "slot1.json"
    path.write_text("{\"sentinel\": 1}", encoding="utf-8")

    def _boom_replace(_src, _dst):
        raise OSError("boom")

    monkeypatch.setattr("engine.persistence_io.os.replace", _boom_replace)

    assert manager.save_game("slot1") is False
    assert json.loads(path.read_text(encoding="utf-8")) == {"sentinel": 1}
    window.player_hud.enqueue_toast.assert_not_called()


def test_snapshot_write_is_atomic_on_replace_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    # Write an existing snapshot file.
    path = Path("saves/quick.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{\"sentinel\": 1}\n", encoding="utf-8")

    class _StubController:
        def __init__(self):
            self.window = MagicMock()
            self.window.engine_config = MagicMock(world_file="worlds/act1_prologue.json")
            self.window.world_controller = MagicMock(id="act1_prologue")
            self.window.scene_controller = MagicMock(current_scene_path="packs/core_regions/scenes/Act1_Prologue_Cabin.json")
            self.state = MagicMock(flags={"a": True}, counters={"gold": 3})

    controller = _StubController()
    controller.window.game_state_controller = controller

    def _boom_replace(_src, _dst):
        raise OSError("boom")

    monkeypatch.setattr("engine.persistence_io.os.replace", _boom_replace)

    assert savegame.save_quick_snapshot(controller.window, path=path) is False
    assert path.read_text(encoding="utf-8") == "{\"sentinel\": 1}\n"
