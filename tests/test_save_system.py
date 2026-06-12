import json
from unittest.mock import MagicMock

from engine.save_manager import SaveManager


class MockWindow:
    def __init__(self):
        self.scene_controller = MagicMock()
        self.game_state_controller = MagicMock()
        self.game_state_controller.export_state.return_value = {}
        self.game_state_controller.import_state = MagicMock()
        self.game_state_controller.replace_state = MagicMock()
        self.scene_controller.current_scene_path = "scenes/test.json"
        self.request_scene_change = MagicMock()

def test_save_game(tmp_path):
    window = MockWindow()
    # Setup mock snapshot
    window.scene_controller.build_scene_snapshot.return_value = {
        "version": 1,
        "state": {"flags": {"test": True}},
        "entities": []
    }

    save_dir = tmp_path / "saves"
    manager = SaveManager(window, save_dir=str(save_dir))

    assert manager.save_game("slot1") is True

    save_file = save_dir / "slot1.json"
    assert save_file.exists()

    with open(save_file, "r") as f:
        data = json.load(f)
        assert data["meta"]["slot"] == "slot1"
        assert data["state"]["flags"]["test"] is True
        assert "game_state" in data

def test_load_game(tmp_path):
    window = MockWindow()
    save_dir = tmp_path / "saves"
    save_dir.mkdir()

    # Create a dummy save file
    save_data = {
        "meta": {"slot": "slot1"},
        "state": {"flags": {"loaded": True}},
        "game_state": {"flags": {"loaded": True}},
        "entities": []
    }
    with open(save_dir / "slot1.json", "w") as f:
        json.dump(save_data, f)

    manager = SaveManager(window, save_dir=str(save_dir))

    assert manager.load_game("slot1") is True

    # Verify state replacement was called
    window.game_state_controller.import_state.assert_called_once_with(save_data["game_state"])

    # Verify scene change was requested with path to save file
    expected_path = str(save_dir / "slot1.json")
    window.request_scene_change.assert_called_once_with(expected_path)

def test_list_saves(tmp_path):
    window = MockWindow()
    save_dir = tmp_path / "saves"
    save_dir.mkdir()

    (save_dir / "slot1.json").touch()
    (save_dir / "slot2.json").touch()
    (save_dir / "config.txt").touch() # Should be ignored

    manager = SaveManager(window, save_dir=str(save_dir))
    saves = manager.list_saves()

    assert len(saves) == 2
    assert "slot1" in saves
    assert "slot2" in saves
