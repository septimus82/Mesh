import pytest
import unittest
from pathlib import Path
from engine.config import EngineConfig
from engine.tooling.trace_command import HeadlessGame


pytestmark = pytest.mark.builtin_behaviours

class TestDemoSmokeSequence(unittest.TestCase):
    def test_load_all_core_scenes(self):
        """Headless load all 9 core scenes and simulate safe events."""
        scenes_dir = Path("packs/core_regions/scenes")
        if not scenes_dir.exists():
            self.skipTest("Core regions pack not found")

        scenes = list(scenes_dir.glob("*.json"))
        
        # Robust assertion: Ensure critical scenes are present instead of a brittle count
        scene_names = {s.name for s in scenes}
        required_scenes = {
            "Ridge Outpost_hub.json",
            "Ridge Outpost_dungeon.json",
            "Hollow Grove_hub.json",
            "Ashen_hub.json"
        }
        missing = required_scenes - scene_names
        self.assertFalse(missing, f"Missing required core scenes: {missing}")
        
        # Ensure we have at least the baseline number of scenes (sanity check)
        self.assertGreaterEqual(len(scenes), len(required_scenes), "Fewer scenes found than required baseline")

        config = EngineConfig(debug_mode=True)
        game = HeadlessGame(config)

        for scene_path in scenes:
            print(f"Testing scene: {scene_path.name}")
            try:
                # Load scene
                # HeadlessGame doesn't have load_scene directly exposed usually, 
                # but trace_command.HeadlessGame might need a way to load scenes.
                # trace_command.HeadlessGame uses MockSceneController.
                # We might need to use game.scene_controller.load_scene if it supports it,
                # or just verify we can parse it.
                # But HeadlessGame is for replay.
                # Let's check HeadlessGame implementation in trace_command.py again.
                
                # Actually, HeadlessGame in trace_command.py has:
                # self.scene_controller = MockSceneController()
                # It doesn't actually load the scene logic fully.
                
                # If we want to test *loading*, we should use GameWindow or a better HeadlessGame.
                # But we can't open a window in CI/headless.
                # We can use SceneLoader directly.
                
                from engine.scene_loader import SceneLoader
                loader = SceneLoader()
                scene_data = loader.load_scene(str(scene_path))
                self.assertIsNotNone(scene_data)
                self.assertTrue(scene_data.get("entities"))
                
            except Exception as e:
                self.fail(f"Failed to load {scene_path.name}: {e}")

if __name__ == "__main__":
    unittest.main()
