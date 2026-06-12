import json
import os
import tempfile
import unittest
from pathlib import Path

from engine.tooling.ai_context_exporter import export_ai_context


class TestAiContextExporter(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.test_dir.name)
        self.prev_cwd = Path.cwd()
        os.chdir(self.root)

        # Setup basic structure
        (self.root / "scenes").mkdir()
        (self.root / "assets/data").mkdir(parents=True)

        # Create dummy quest definitions
        (self.root / "assets/data/quests.json").write_text(json.dumps({
            "quests": [
                {"id": "test_quest", "title": "Test Quest"}
            ]
        }))

    def tearDown(self):
        os.chdir(self.prev_cwd)
        self.test_dir.cleanup()

    def test_export_single_scene(self):
        scene_path = self.root / "scenes/test_hub.json"
        scene_path.write_text(json.dumps({
            "entities": [
                {
                    "name": "Guard",
                    "x": 10,
                    "y": 20,
                    "tag": "npc",
                    "tags": ["guard"],
                    "dialogue": {"id": "guard_intro"}
                },
                {
                    "name": "Door",
                    "behaviours": ["SceneTransition"],
                    "behaviour_config": {
                        "SceneTransition": {"target_scene": "scenes/other.json"}
                    }
                },
                {
                    "name": "Giver",
                    "tag": "npc",
                    "behaviours": ["QuestGiver"],
                    "behaviour_config": {
                        "QuestGiver": {"quest_id": "test_quest"}
                    }
                }
            ]
        }))

        context = export_ai_context([scene_path])

        self.assertIn("scenes", context)
        self.assertEqual(len(context["scenes"]), 1)

        summary = context["scenes"][0]
        self.assertEqual(summary["scene_id"], "test_hub")
        self.assertEqual(summary["kind"], "overworld") # inferred from 'hub'

        # Check NPCs
        self.assertEqual(len(summary["npcs"]), 2)
        guard = next(n for n in summary["npcs"] if n["name"] == "Guard")
        self.assertEqual(guard["role"], "guard")
        self.assertEqual(guard["dialogue_id"], "guard_intro")
        self.assertEqual(guard["position"], {"x": 10, "y": 20})

        # Check Transitions
        self.assertEqual(len(summary["transitions"]), 1)
        self.assertEqual(summary["transitions"][0]["to_scene"], "scenes/other.json")
        self.assertEqual(summary["transitions"][0]["kind"], "door")

        # Check Quests
        self.assertEqual(len(summary["quests"]), 1)
        self.assertEqual(summary["quests"][0]["id"], "test_quest")
        self.assertEqual(summary["quests"][0]["title"], "Test Quest")

        # Check Summary Counts
        self.assertEqual(summary["summary"]["npc_count"], 2)
        self.assertEqual(summary["summary"]["transition_count"], 1)
        self.assertEqual(summary["summary"]["quest_hook_count"], 1)

    def test_export_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            export_ai_context([Path("scenes/missing.json")])

    def test_export_invalid_json(self):
        scene_path = self.root / "scenes/bad.json"
        scene_path.write_text("{ invalid json")
        with self.assertRaises(ValueError):
            export_ai_context([scene_path])
