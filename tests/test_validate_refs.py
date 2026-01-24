import unittest
import tempfile
import shutil
import json
from pathlib import Path
from engine.validators.reference_validator import ReferenceValidator
from engine.paths import set_content_roots, get_content_roots

class TestReferenceValidator(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.assets_dir = self.test_dir / "assets"
        self.assets_dir.mkdir()
        
        self.original_roots = get_content_roots()
        set_content_roots([self.assets_dir])
        
        # Create dummy assets
        (self.assets_dir / "sprite.png").write_text("")
        (self.assets_dir / "tiles.json").write_text("{}")
        
        # Create scene
        self.scene_path = self.assets_dir / "scene.json"
        self.scene_data = {
            "tilemap": "tiles.json",
            "entities": [
                {"id": "e1", "sprite": "sprite.png"},
                {"id": "e2", "sprite": "missing.png"}
            ]
        }
        self.scene_path.write_text(json.dumps(self.scene_data))
        
        # Create world
        self.world_path = self.assets_dir / "world.json"
        self.world_data = {
            "initial_scene": "scene.json"
        }
        self.world_path.write_text(json.dumps(self.world_data))

    def tearDown(self):
        shutil.rmtree(self.test_dir)
        set_content_roots(self.original_roots)

    def test_validate_refs(self):
        validator = ReferenceValidator(str(self.world_path))
        success = validator.validate()
        
        self.assertFalse(success)
        self.assertTrue(any("missing.png" in e for e in validator.errors))
        self.assertFalse(any("sprite.png" in e for e in validator.errors))
        self.assertFalse(any("tiles.json" in e for e in validator.errors))

    def test_validate_missing_scene(self):
        self.world_data["initial_scene"] = "missing_scene.json"
        self.world_path.write_text(json.dumps(self.world_data))
        
        validator = ReferenceValidator(str(self.world_path))
        success = validator.validate()
        
        self.assertFalse(success)
        self.assertTrue(any("missing_scene.json" in e for e in validator.errors))
