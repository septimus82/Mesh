import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine import ai_history

class TestAIHistory(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.history_path = Path(self.temp_dir.name) / "ai_history.jsonl"
        # Patch the HISTORY_FILE in ai_history module
        self.patcher = patch("engine.ai_history.HISTORY_FILE", self.history_path)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        self.temp_dir.cleanup()

    def test_append_and_load(self):
        ai_history.append_history_entry("plan1.json", ["scene1", "scene2"], goal="Fix stuff")
        entries = ai_history.load_history()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["plan_path"], "plan1.json")
        self.assertEqual(entries[0]["scenes_touched"], ["scene1", "scene2"])
        self.assertEqual(entries[0]["goal"], "Fix stuff")
        self.assertEqual(entries[0]["result"], "applied")
        self.assertIn("timestamp", entries[0])

    def test_filter(self):
        ai_history.append_history_entry("plan1.json", ["scene1"])
        ai_history.append_history_entry("plan2.json", ["scene2"])
        ai_history.append_history_entry("plan3.json", ["scene1", "scene2"])

        entries = ai_history.load_history()
        
        # Filter by scene
        s1 = ai_history.filter_history(entries, scene="scene1")
        self.assertEqual(len(s1), 2)
        self.assertEqual(s1[0]["plan_path"], "plan1.json")
        self.assertEqual(s1[1]["plan_path"], "plan3.json")

        # Filter by plan
        p2 = ai_history.filter_history(entries, plan_path="plan2.json")
        self.assertEqual(len(p2), 1)
        self.assertEqual(p2[0]["plan_path"], "plan2.json")

    def test_extract_scenes(self):
        plan_data = {
            "actions": [
                {"type": "create_scene", "args": {"path": "scenes/new_scene.json"}},
                {"type": "add_npc", "args": {"scene_path": "scenes/hub.json"}},
                {"type": "add_transition", "args": {"from_scene": "scenes/hub.json", "to_scene": "scenes/dungeon.json"}},
                {"type": "place_npc", "args": {"into": "scenes/hub.json"}}
            ]
        }
        scenes = ai_history.extract_scenes_from_plan(plan_data)
        self.assertEqual(scenes, ["dungeon", "hub", "new_scene"])

    def test_extract_scenes_from_objects(self):
        # Mock Action objects
        class MockAction:
            def __init__(self, type, args):
                self.type = type
                self.args = args
        
        actions = [
            MockAction("create_scene", {"path": "scenes/new_scene.json"}),
            MockAction("add_npc", {"scene_path": "scenes/hub.json"})
        ]
        # extract_scenes_from_plan expects a dict with "actions" list
        scenes = ai_history.extract_scenes_from_plan({"actions": actions})
        self.assertEqual(scenes, ["hub", "new_scene"])
