import json
from pathlib import Path

import pytest

from engine.inventory import load_item_database
from engine.quests import QuestManager
from engine.scene_loader import SceneLoader

pytestmark = pytest.mark.builtin_behaviours

def test_world_structure():
    world_path = Path("worlds/main_world.json")
    assert world_path.exists()

    with open(world_path, "r") as f:
        world = json.load(f)

    assert "scenes" in world
    assert "door_field" in world["scenes"]
    assert "door_interior" in world["scenes"]
    assert "cellar" in world["scenes"]

    loader = SceneLoader()
    for scene_key, scene_def in world["scenes"].items():
        path = scene_def["path"]
        assert Path(path).exists(), f"Scene {scene_key} path {path} missing"
        # Try loading
        scene = loader.load_scene(path)
        assert scene.get("name"), f"Scene {scene_key} missing name"

def test_quest_definitions():
    # Mock window for QuestManager
    class MockGameState:
        def __init__(self):
            self.values = {}

    class MockWindow:
        def __init__(self):
            self.game_state = MockGameState()

        def emit_signal(self, *args, **kwargs):
            pass

    qm = QuestManager(MockWindow(), "assets/data/quests.json")
    assert "field_supplies" in qm._definitions
    quest = qm._definitions["field_supplies"]
    assert len(quest["stages"]) >= 2

def test_item_definitions():
    db = load_item_database()
    assert db.get("golden_rat_statue") is not None
    assert db.get("golden_rat_statue").name == "Golden Rat Statue"
