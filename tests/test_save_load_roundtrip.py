import json
import pytest
from unittest.mock import MagicMock, patch
from engine.save_manager import SaveManager
from engine.game_state_controller import GameStateController

class RealLogicWindow:
    def __init__(self):
        self.width = 800
        self.height = 600
        self.game_state_controller = GameStateController(self)
        self.scene_controller = MagicMock()
        self.scene_controller.current_scene_path = "scenes/test_scene.json"
        self.scene_controller.build_scene_snapshot.return_value = {
            "entities": [{"id": "e1", "x": 10, "y": 20}],
            "settings": {"camera": {}}
        }
        self.request_scene_change = MagicMock()
        self.camera_controller = MagicMock()
        self.camera_controller.zoom_state.current = 1.0
        self.camera_controller.zoom_state.target = 1.0
        self.camera_controller.zoom_state.speed = 0.1
        self.camera_controller.zoom_state.min_zoom = 0.5
        self.camera_controller.zoom_state.max_zoom = 2.0

def test_round_trip_determinism(tmp_path):
    window = RealLogicWindow()
    
    # Populate Game State
    gs = window.game_state_controller.state
    gs.counters["gold"] = 100
    gs.flags["boss_defeated"] = True
    gs.equipment["weapon"] = "sword_01"
    gs.perks = ["perk_b", "perk_a"] # Unsorted
    gs.xp = 500
    gs.level = 5
    
    # Save
    save_dir = tmp_path / "saves"
    manager = SaveManager(window, save_dir=str(save_dir))
    manager.save_game("test_slot")
    
    save_path = save_dir / "test_slot.json"
    assert save_path.exists()
    
    # Load raw JSON to check determinism
    with open(save_path, "r") as f:
        data = json.load(f)
        
    # Check Version
    assert data["meta"]["version"] == 2
    
    # Check Sorted Perks
    assert data["game_state"]["perks"] == ["perk_a", "perk_b"]
    
    # Load into fresh window
    new_window = RealLogicWindow()
    new_manager = SaveManager(new_window, save_dir=str(save_dir))
    
    new_manager.load_game("test_slot")
    
    new_gs = new_window.game_state_controller.state
    assert new_gs.counters["gold"] == 100
    assert new_gs.flags["boss_defeated"] is True
    assert new_gs.equipment["weapon"] == "sword_01"
    assert new_gs.perks == ["perk_a", "perk_b"]
    assert new_gs.xp == 500
    assert new_gs.level == 5

def test_load_old_version(tmp_path):
    # Create a v0 save (no version field)
    save_data = {
        "meta": {
            "slot": "old_slot",
            "scene_path": "scenes/old.json",
            "timestamp": "2020-01-01"
        },
        "game_state": {
            "counters": {"gold": 50},
            "flags": {},
            "perks": ["old_perk"]
        },
        "entities": []
    }
    
    save_dir = tmp_path / "saves"
    save_dir.mkdir()
    with open(save_dir / "old_slot.json", "w") as f:
        json.dump(save_data, f)
        
    window = RealLogicWindow()
    manager = SaveManager(window, save_dir=str(save_dir))
    
    assert manager.load_game("old_slot") is True
    
    gs = window.game_state_controller.state
    assert gs.counters["gold"] == 50
    assert gs.perks == ["old_perk"]

def test_file_determinism(tmp_path):
    # Verify that the file content is identical for identical states (ignoring timestamp/slot)
    window = RealLogicWindow()
    window.game_state_controller.state.counters["gold"] = 100
    window.game_state_controller.state.perks = ["z", "a"]
    
    save_dir = tmp_path / "saves"
    manager = SaveManager(window, save_dir=str(save_dir))
    
    # Mock timestamp to be constant
    with patch.object(manager, '_get_timestamp', return_value="2025-01-01T00:00:00"):
        manager.save_game("slot_det")
        
    with open(save_dir / "slot_det.json", "r") as f:
        content = f.read()
        
    # Check if perks are sorted in the file text
    # "perks": [
    #   "a",
    #   "z"
    # ]
    # We look for "a" appearing before "z" in the perks section
    perks_index = content.find('"perks": [')
    a_index = content.find('"a"', perks_index)
    z_index = content.find('"z"', perks_index)
    
    assert perks_index != -1
    assert a_index != -1
    assert z_index != -1
    assert a_index < z_index

