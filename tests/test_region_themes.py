import pytest
import json
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from engine.tooling import scaffold


pytestmark = pytest.mark.builtin_behaviours

class TestRegionThemes(unittest.TestCase):
    def setUp(self):
        self.mock_themes = {
            "moss": {
                "description": "Mossy",
                "default_enemy_tags": ["plant"],
                "default_drop_table_id": "nature_drops",
                "ambient_audio_key": "forest_ambience",
                "lighting_hint": "green_dim"
            }
        }

    @patch("engine.tooling.scaffold.Path")
    @patch("engine.tooling.scaffold.SceneLoader")
    def test_create_scene_with_theme(self, MockLoader, MockPath):
        # Setup Mocks
        mock_path_obj = MagicMock()
        mock_path_obj.exists.return_value = False # Target scene doesn't exist
        mock_path_obj.stem = "test_scene" # Fix for json serialization
        
        # Mock themes.json read
        mock_themes_path = MagicMock()
        mock_themes_path.exists.return_value = True
        mock_themes_path.read_text.return_value = json.dumps(self.mock_themes)
        
        def path_side_effect(arg):
            if str(arg).endswith("themes.json"):
                return mock_themes_path
            return mock_path_obj
            
        MockPath.side_effect = path_side_effect

        # Mock Loader
        mock_loader_instance = MockLoader.return_value
        mock_loader_instance.apply_scene_defaults.side_effect = lambda x: x # Identity

        # Call create_scene
        scaffold.create_scene("scenes/test_scene.json", "empty", extra_args={"region_theme": "moss"})

        # Verify write
        handle = mock_path_obj.open.return_value.__enter__.return_value
        args, _ = handle.write.call_args
        written_json = args[0] # It might be json.dump call, let's check
        
        # json.dump is called on handle
        # Wait, scaffold uses json.dump(compacted, handle, ...)
        # So we need to check the call to json.dump if we mocked open?
        # Actually scaffold.py does:
        # with target_path.open("w", encoding="utf-8") as handle:
        #     json.dump(final_scene, handle, indent=2, sort_keys=False)
        
        # Since we can't easily intercept json.dump with just Path mock unless we mock json too,
        # let's inspect what was passed to compact_scene_payload or apply_scene_defaults.
        
        call_args = mock_loader_instance.apply_scene_defaults.call_args
        scene_data = call_args[0][0]
        
        self.assertEqual(scene_data["settings"]["region_theme"], "moss")
        self.assertEqual(scene_data["settings"]["lighting_hint"], "green_dim")
        self.assertEqual(scene_data["settings"]["ambient_audio"], "forest_ambience")

if __name__ == "__main__":
    unittest.main()
