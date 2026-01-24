from __future__ import annotations

from unittest.mock import MagicMock

from engine.save_manager import SaveManager


class _SaveManagerWindow:
    def __init__(self) -> None:
        self.scene_controller = MagicMock()
        self.scene_controller.current_scene_path = "scenes/test.json"
        self.scene_controller.build_scene_snapshot.return_value = {
            "camera": {"x": 0, "y": 0},
            "entities": [],
            "settings": {"weather": "clear"},
        }
        self.game_state_controller = MagicMock()
        self.game_state_controller.export_state.return_value = {
            "flags": {"alpha": True, "beta": False, "gamma": True},
            "counters": {"gold": 12},
            "perks": ["starter"],
        }
        self.player_hud = MagicMock()


def test_save_manager_output_bytes_are_deterministic(tmp_path, monkeypatch):
    window = _SaveManagerWindow()
    manager = SaveManager(window, save_dir=str(tmp_path))

    # SaveManager includes a timestamp in the JSON; freeze it so this test
    # can assert byte-for-byte determinism.
    monkeypatch.setattr(manager, "_get_timestamp", lambda: "2000-01-01T00:00:00")

    assert manager.save_game("slot1") is True
    path = manager.get_save_path("slot1")
    first = path.read_bytes()

    assert manager.save_game("slot1") is True
    second = path.read_bytes()

    assert first == second

    # Standard policy: JSON saves end with a single trailing newline.
    assert first.endswith(b"\n")
