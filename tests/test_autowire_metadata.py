import unittest
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from engine.tooling.auto_wire import AutoWireController

class TestAutoWireMetadata(unittest.TestCase):
    def setUp(self):
        self.controller = AutoWireController("dummy_world.json")
        self.controller.scenes = {}
        self.controller._add_transition = MagicMock(return_value=True)
        self.controller._save_changes = MagicMock()

    def test_ruins_wiring(self):
        # Setup mock scenes with metadata
        self.controller.scenes = {
            "Ruins_hub": {
                "settings": {"region_template": "ruins", "scene_kind": "hub"},
                "entities": []
            },
            "Ruins_path": {
                "settings": {"region_template": "ruins", "scene_kind": "path"},
                "entities": []
            },
            "Ruins_dungeon": {
                "settings": {"region_template": "ruins", "scene_kind": "dungeon"},
                "entities": []
            }
        }
        
        changes = self.controller.process(dry_run=True)
        
        # Verify links
        # Hub <-> Path
        self.controller._add_transition.assert_any_call("Ruins_hub", "Ruins_path")
        self.controller._add_transition.assert_any_call("Ruins_path", "Ruins_hub")
        
        # Path <-> Dungeon
        self.controller._add_transition.assert_any_call("Ruins_path", "Ruins_dungeon")
        self.controller._add_transition.assert_any_call("Ruins_dungeon", "Ruins_path")
        
        # Ensure NO direct Hub <-> Dungeon link (unless path missing, but here it exists)
        # The logic I wrote doesn't explicitly forbid it, but it only adds what's in the rules.
        # Ruins rules: Hub <-> Path, Path <-> Dungeon.
        # So Hub <-> Dungeon should NOT be called.
        
        # We can check calls.
        calls = [c[0] for c in self.controller._add_transition.call_args_list]
        self.assertNotIn(("Ruins_hub", "Ruins_dungeon"), calls)
        self.assertNotIn(("Ruins_dungeon", "Ruins_hub"), calls)

    def test_deep_dungeon_wiring(self):
        self.controller.scenes = {
            "Deep_entry": {
                "settings": {"region_template": "deep-dungeon", "scene_kind": "entry"},
                "entities": []
            },
            "Deep_depths": {
                "settings": {"region_template": "deep-dungeon", "scene_kind": "depths"},
                "entities": []
            }
        }
        
        self.controller.process(dry_run=True)
        
        self.controller._add_transition.assert_any_call("Deep_entry", "Deep_depths")
        self.controller._add_transition.assert_any_call("Deep_depths", "Deep_entry")

    def test_fallback_heuristic(self):
        # Legacy scenes without metadata
        self.controller.scenes = {
            "Legacy_hub": {"settings": {}, "entities": []},
            "Legacy_interior": {"settings": {}, "entities": []}
        }
        
        self.controller.process(dry_run=True)
        
        self.controller._add_transition.assert_any_call("Legacy_hub", "Legacy_interior")
        self.controller._add_transition.assert_any_call("Legacy_interior", "Legacy_hub")

if __name__ == "__main__":
    unittest.main()
