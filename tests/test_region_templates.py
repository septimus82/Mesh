import unittest
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from engine.tooling.wizard_command import WizardContext, _plan_new_region
from engine.tooling.plan_types import Action

class TestRegionTemplates(unittest.TestCase):
    def setUp(self):
        self.args = MagicMock()
        self.args.name_prefix = "TestRegion"
        self.args.pack = None
        self.args.into_world = None
        self.args.with_boss = False
        self.args.with_puzzle = False
        self.args.perks = None
        self.args.profile = "safe"
        self.args.link_from = None
        
        self.ctx = WizardContext(self.args)
        self.ctx.add_action = MagicMock()
        self.ctx.resolve_path = lambda p: Path(p)

    def test_default_template(self):
        self.args.template = None # Default
        _plan_new_region(self.ctx)
        
        # Check scenes created
        created_scenes = []
        for call in self.ctx.add_action.call_args_list:
            if call[0][0] == "create_scene":
                created_scenes.append(str(Path(call[0][1]["path"])))
                
        self.assertIn(str(Path("scenes/TestRegion_hub.json")), created_scenes)
        self.assertIn(str(Path("scenes/TestRegion_interior.json")), created_scenes)
        self.assertIn(str(Path("scenes/TestRegion_dungeon.json")), created_scenes)

    def test_ruins_template(self):
        self.args.template = "ruins"
        _plan_new_region(self.ctx)
        
        created_scenes = []
        metadata = {}
        for call in self.ctx.add_action.call_args_list:
            if call[0][0] == "create_scene":
                path = str(Path(call[0][1]["path"]))
                created_scenes.append(path)
                metadata[path] = {
                    "kind": call[0][1].get("scene_kind"),
                    "template": call[0][1].get("region_template")
                }
                
        self.assertIn(str(Path("scenes/TestRegion_hub.json")), created_scenes)
        self.assertIn(str(Path("scenes/TestRegion_path.json")), created_scenes)
        self.assertIn(str(Path("scenes/TestRegion_dungeon.json")), created_scenes)
        
        # Check metadata
        hub_path = str(Path("scenes/TestRegion_hub.json"))
        self.assertEqual(metadata[hub_path]["kind"], "hub")
        self.assertEqual(metadata[hub_path]["template"], "ruins")
        
        path_path = str(Path("scenes/TestRegion_path.json"))
        self.assertEqual(metadata[path_path]["kind"], "path")
        self.assertEqual(metadata[path_path]["template"], "ruins")

    def test_deep_dungeon_template(self):
        self.args.template = "deep-dungeon"
        _plan_new_region(self.ctx)
        
        created_scenes = []
        for call in self.ctx.add_action.call_args_list:
            if call[0][0] == "create_scene":
                created_scenes.append(str(Path(call[0][1]["path"])))
                
        self.assertIn(str(Path("scenes/TestRegion_entry.json")), created_scenes)
        self.assertIn(str(Path("scenes/TestRegion_depths.json")), created_scenes)
        self.assertNotIn(str(Path("scenes/TestRegion_hub.json")), created_scenes)

if __name__ == "__main__":
    unittest.main()
