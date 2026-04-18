import unittest
import json
from pathlib import Path
from engine.config import load_config

class TestGoldenSliceContentInvariants(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.presets_to_check = [
            "golden_slice",
            "golden_slice_variant_b",
            "golden_slice_variant_c",
            "golden_slice_variant_d",
            "golden_slice_variant_e",
            "golden_slice_variant_f",
            "golden_slice_variant_g",
        ]

    def _get_dungeon_scene_path(self, preset_name):
        preset = self.config.presets.get(preset_name)
        self.assertIsNotNone(preset, f"Preset {preset_name} not found in config")
        
        steps = preset.get("steps") if isinstance(preset, dict) else preset
        self.assertIsInstance(steps, list, f"Preset {preset_name} steps must be a list")
        
        # Find the pipeline command with --world arg
        world_path = None
        for step in steps:
            if step.get("cmd") == "pipeline":
                args = step.get("args", [])
                if "--world" in args:
                    idx = args.index("--world")
                    if idx + 1 < len(args):
                        world_path = args[idx + 1]
                        break
        
        self.assertIsNotNone(world_path, f"Could not find --world arg in preset {preset_name}")
        
        # Load world file
        world_file = Path(world_path)
        self.assertTrue(world_file.exists(), f"World file {world_path} does not exist")
        
        with open(world_file, "r", encoding="utf-8") as f:
            world_data = json.load(f)
            
        # Find dungeon scene
        # We look for a scene with key "Ridge Outpost_dungeon" or similar, or tag "dungeon"
        # But specifically we want the Ridge Outpost dungeon for these variants.
        scene_entry = world_data.get("scenes", {}).get("Ridge Outpost_dungeon")
        self.assertIsNotNone(scene_entry, f"Ridge Outpost_dungeon scene not found in world {world_path}")
        
        scene_path = scene_entry.get("path")
        self.assertIsNotNone(scene_path, f"Path not found for Ridge Outpost_dungeon in world {world_path}")
        
        return Path(scene_path)

    def _load_scene(self, path):
        self.assertTrue(path.exists(), f"Scene file {path} does not exist")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_golden_slice_invariants(self):
        for preset_name in self.presets_to_check:
            with self.subTest(preset=preset_name):
                scene_path = self._get_dungeon_scene_path(preset_name)
                scene_data = self._load_scene(scene_path)
                
                entities = scene_data.get("entities", [])
                
                # 1. Find Boss
                bosses = []
                for e in entities:
                    vid = e.get("variant_id", "")
                    name = e.get("name") or e.get("mesh_name", "")
                    tags = e.get("tags", [])
                    if isinstance(e.get("tag"), str):
                        tags.append(e.get("tag"))
                        
                    is_boss = (
                        "boss" in vid.lower() or 
                        "boss" in name.lower() or 
                        "boss" in tags
                    )
                    if is_boss:
                        bosses.append(e)
                
                self.assertEqual(len(bosses), 1, f"Expected exactly one boss in {scene_path}, found {len(bosses)}")
                boss = bosses[0]
                
                # 2. Boss has DropTable
                behaviours = boss.get("behaviours", [])
                self.assertIn("DropTable", behaviours, f"Boss in {scene_path} missing DropTable behaviour")
                
                # 3. Boss reward clarity (name/id)
                name = boss.get("name") or boss.get("mesh_name")
                self.assertTrue(name, f"Boss in {scene_path} missing name/mesh_name for toast clarity")
                
                # 4. Exit behind boss
                exits = [
                    e
                    for e in entities
                    if e.get("name") == "Exit"
                    or "door" in (
                        e.get("tags", [])
                        if isinstance(e.get("tags"), list)
                        else [e.get("tag", "")]
                    )
                ]
                # Filter for the actual exit to hub, usually named "Exit" or having SceneTransition to hub
                # In these scenes, it's named "Exit"
                main_exit = next((e for e in exits if e.get("name") == "Exit"), None)
                self.assertIsNotNone(main_exit, f"Exit entity not found in {scene_path}")
                
                boss_x = boss.get("x", 0)
                exit_x = main_exit.get("x", 0)
                
                self.assertGreater(exit_x, boss_x, f"Exit (x={exit_x}) must be behind Boss (x={boss_x}) in {scene_path}")
                
                # 5. Elite before boss (if present)
                elites = []
                for e in entities:
                    vid = e.get("variant_id", "")
                    name = e.get("name") or e.get("mesh_name", "")
                    if "elite" in vid.lower() or "elite" in name.lower():
                        elites.append(e)
                
                for elite in elites:
                    elite_x = elite.get("x", 0)
                    self.assertLess(elite_x, boss_x, f"Elite (x={elite_x}) must be before Boss (x={boss_x}) in {scene_path}")

if __name__ == "__main__":
    unittest.main()
