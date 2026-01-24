import json
import shutil
import unittest
from pathlib import Path
from engine.tooling.validate_all import UnifiedValidator

class TestWorldReachability(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("tests/temp_reachability")
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.test_dir.mkdir()
        (self.test_dir / "scenes").mkdir()

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def create_dummy_scene(self, name):
        path = self.test_dir / "scenes" / f"{name}.json"
        data = {"name": name, "version": 1, "entities": [], "layers": []}
        with open(path, "w") as f:
            json.dump(data, f)
        return str(path.relative_to(self.test_dir))

    def test_reachability(self):
        # Create scenes
        p1 = self.create_dummy_scene("s1")
        p2 = self.create_dummy_scene("s2")
        p3 = self.create_dummy_scene("s3")
        
        # World where s1 -> s2, but s3 is unreachable
        world_data = {
            "start_scene": "s1",
            "scenes": {
                "s1": {"path": p1},
                "s2": {"path": p2},
                "s3": {"path": p3}
            },
            "links": [
                {"from": "s1", "to": "s2"}
            ]
        }
        
        validator = UnifiedValidator(self.test_dir, check_reachability=True)
        validator.check_reachability(world_data)
        
        warnings = "\n".join(validator.warnings)
        self.assertIn("Scene 's3' is unreachable", warnings)

    def test_orphans(self):
        # Create scenes
        p1 = self.create_dummy_scene("s1")
        self.create_dummy_scene("orphan")
        
        world_data = {
            "scenes": {
                "s1": {"path": p1}
            },
            "links": []
        }
        
        validator = UnifiedValidator(self.test_dir, check_orphans=True)
        validator.check_orphans(world_data, self.test_dir / "world.json")
        
        warnings = "\n".join(validator.warnings)
        self.assertIn("Orphan scene file found", warnings)
        self.assertIn("orphan.json", warnings)

if __name__ == "__main__":
    unittest.main()
