import json
import shutil
import unittest
from pathlib import Path

from engine.tooling import scaffold


class TestToolingNewPrefab(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("tests/temp_prefab")
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.test_dir.mkdir()

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_extract_prefab(self):
        scene_path = self.test_dir / "scene.json"
        prefabs_path = self.test_dir / "prefabs.json"

        # Create scene with entity
        scene_data = {
            "name": "Scene",
            "version": 1,
            "entities": [
                {
                    "name": "UniqueEntity",
                    "x": 100,
                    "y": 200,
                    "sprite": "assets/unique.png",
                    "behaviours": ["Custom"]
                }
            ],
            "layers": []
        }
        with open(scene_path, "w") as f:
            json.dump(scene_data, f)

        # Extract
        self.assertTrue(scaffold.extract_prefab(
            "unique_prefab",
            str(scene_path),
            "UniqueEntity",
            remove_source=True,
            target_file=str(prefabs_path)
        ))

        # Check prefabs.json
        self.assertTrue(prefabs_path.exists())
        with open(prefabs_path, "r") as f:
            prefabs = json.load(f)
            self.assertEqual(len(prefabs), 1)
            self.assertEqual(prefabs[0]["id"], "unique_prefab")
            self.assertEqual(prefabs[0]["entity"]["name"], "UniqueEntity")
            self.assertNotIn("x", prefabs[0]["entity"]) # Should be stripped

        # Check scene (source removed)
        with open(scene_path, "r") as f:
            scene = json.load(f)
            self.assertEqual(len(scene.get("entities", [])), 0)

if __name__ == "__main__":
    unittest.main()
