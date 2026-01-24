import unittest
import shutil
import json
from pathlib import Path
from engine.tooling import scaffold

class TestToolingPlacePrefab(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("tests/temp_place_prefab")
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.test_dir.mkdir()
        
    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_place_prefab(self):
        scene_path = self.test_dir / "scene.json"
        prefabs_path = self.test_dir / "prefabs.json"
        
        # Create prefabs file
        prefabs_data = [
            {
                "id": "test_prefab",
                "entity": {
                    "name": "TestEntity",
                    "sprite": "test.png"
                }
            }
        ]
        with open(prefabs_path, "w") as f:
            json.dump(prefabs_data, f)
        
        # Create scene file
        scene_data = {
            "name": "Scene",
            "version": 1,
            "entities": [],
            "layers": []
        }
        with open(scene_path, "w") as f:
            json.dump(scene_data, f)
            
        # Place prefab
        # We need to mock UnifiedValidator because it will fail on missing sprite/assets
        from unittest.mock import patch
        with patch("engine.tooling.validate_all.UnifiedValidator") as MockValidator:
            instance = MockValidator.return_value
            instance.validate_scene.return_value = True
            
            self.assertTrue(scaffold.place_prefab(
                "test_prefab", 
                str(scene_path), 
                100, 
                200, 
                prefabs_file=str(prefabs_path)
            ))
            
        # Verify
        with open(scene_path, "r") as f:
            data = json.load(f)
            self.assertEqual(len(data["entities"]), 1)
            ent = data["entities"][0]
            # New behavior: places reference
            self.assertEqual(ent["prefab_id"], "test_prefab")
            self.assertEqual(ent["x"], 100)
            self.assertEqual(ent["y"], 200)

if __name__ == "__main__":
    unittest.main()
