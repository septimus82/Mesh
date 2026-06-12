import unittest

from engine.config import EngineConfig, load_config
from engine.paths import resolve_path


class TestConfigStartSceneExists(unittest.TestCase):
    def test_start_scene_exists(self):
        """Ensure the configured start_scene actually exists on disk."""
        config = load_config()
        start_scene = config.start_scene

        # Resolve path relative to workspace root
        # resolve_path handles relative paths correctly
        full_path = resolve_path(start_scene)

        self.assertTrue(full_path.exists(), f"Start scene '{start_scene}' does not exist at {full_path}")
        self.assertTrue(full_path.is_file(), f"Start scene '{start_scene}' is not a file")

    def test_default_start_scene_exists(self):
        """Ensure the default start_scene in EngineConfig exists."""
        default_config = EngineConfig()
        start_scene = default_config.start_scene
        full_path = resolve_path(start_scene)

        self.assertTrue(full_path.exists(), f"Default start scene '{start_scene}' does not exist at {full_path}")
