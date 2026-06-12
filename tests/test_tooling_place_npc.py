import json
import shutil
import unittest
from pathlib import Path

from engine.tooling import scaffold


class TestToolingPlaceNPC(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("tests/temp_place_npc")
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.test_dir.mkdir()

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_place_npc(self):
        scene_path = self.test_dir / "scene.json"

        # Create scene file
        scene_data = {
            "name": "Scene",
            "version": 1,
            "entities": [],
            "layers": []
        }
        with open(scene_path, "w") as f:
            json.dump(scene_data, f)

        # Place NPC
        self.assertTrue(scaffold.create_npc(
            "guard",
            str(scene_path),
            100,
            200
        ))

        # Verify
        with open(scene_path, "r") as f:
            data = json.load(f)
            self.assertEqual(len(data["entities"]), 1)
            ent = data["entities"][0]
            self.assertEqual(ent["name"], "Guard")
            self.assertEqual(ent["x"], 100)
            self.assertEqual(ent["y"], 200)

if __name__ == "__main__":
    unittest.main()
