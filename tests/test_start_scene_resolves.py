import unittest
from engine.config import EngineConfig
from engine.paths import resolve_path

class TestStartSceneResolves(unittest.TestCase):
    def test_start_scene_resolves(self):
        config = EngineConfig()
        # Load from config.json if it exists, but EngineConfig defaults might be used if not loaded explicitly.
        # The task says "Load EngineConfig using the existing config loader."
        from engine.config import load_config
        config = load_config()
        
        start_scene = config.start_scene
        print(f"Start scene: {start_scene}")
        
        path = resolve_path(start_scene)
        self.assertTrue(path.exists(), f"Start scene '{start_scene}' does not exist at '{path}'")

if __name__ == "__main__":
    unittest.main()
