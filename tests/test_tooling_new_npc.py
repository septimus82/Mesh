import json
import shutil
import unittest
from pathlib import Path
from engine.tooling import scaffold

class TestToolingNewNPC(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("tests/temp_npc")
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.test_dir.mkdir()

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_create_npc_in_scene(self):
        scene_path = self.test_dir / "scene.json"
        data = {"name": "Scene", "version": 1, "entities": [], "layers": []}
        with open(scene_path, "w") as f:
            json.dump(data, f)
            
        self.assertTrue(scaffold.create_npc("guard", str(scene_path), x=100, y=200))
        
        with open(scene_path, "r") as f:
            data = json.load(f)
            self.assertEqual(len(data["entities"]), 1)
            npc = data["entities"][0]
            self.assertEqual(npc["name"], "Guard")
            self.assertEqual(npc["x"], 100)
            self.assertEqual(npc["y"], 200)

    def test_invalid_role(self):
        self.assertFalse(scaffold.create_npc("wizard"))

if __name__ == "__main__":
    unittest.main()
