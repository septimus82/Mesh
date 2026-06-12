import json
import shutil
import unittest
from pathlib import Path

from engine.tooling import polish


class TestToolingPolish(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("tests/temp_polish")
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.test_dir.mkdir()

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_polish_scene(self):
        # Create a non-compact scene
        scene_path = self.test_dir / "messy_scene.json"
        data = {
            "name": "Messy",
            "version": 1,
            "settings": {"background_color": "dark_blue_gray"}, # Default value
            "entities": [],
            "layers": []
        }
        with open(scene_path, "w") as f:
            json.dump(data, f)

        # Polish it
        self.assertTrue(polish.polish_scene(scene_path))

        # Check if compacted
        with open(scene_path, "r") as f:
            polished = json.load(f)
            self.assertNotIn("settings", polished) # Should be removed as it was default

    def test_polish_world(self):
        # Create world and scene
        world_path = self.test_dir / "world.json"
        scene_path = self.test_dir / "scene.json"

        scene_data = {
            "name": "Scene",
            "version": 1,
            "settings": {"background_color": "dark_blue_gray"},
            "entities": [],
            "layers": []
        }
        with open(scene_path, "w") as f:
            json.dump(scene_data, f)

        world_data = {
            "scenes": {
                "main": {"path": str(scene_path)}
            },
            "links": []
        }
        with open(world_path, "w") as f:
            json.dump(world_data, f)

        # Polish world with compact_scenes=True
        self.assertTrue(polish.polish_world(world_path, compact_scenes=True))

        # Check scene
        with open(scene_path, "r") as f:
            polished_scene = json.load(f)
            self.assertNotIn("settings", polished_scene)

if __name__ == "__main__":
    unittest.main()
