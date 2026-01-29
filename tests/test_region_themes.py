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

        call_args = mock_loader_instance.apply_scene_defaults.call_args
        scene_data = call_args[0][0]
        
        self.assertEqual(scene_data["settings"]["region_theme"], "moss")
        self.assertEqual(scene_data["settings"]["lighting_hint"], "green_dim")
        self.assertEqual(scene_data["settings"]["ambient_audio"], "forest_ambience")

if __name__ == "__main__":
    unittest.main()
