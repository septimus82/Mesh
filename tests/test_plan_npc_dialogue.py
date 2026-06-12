import json
import os
import tempfile
import unittest
from pathlib import Path

from engine.tooling.plan_executor import PlanExecutor
from engine.tooling.plan_linter import lint_ai_plan
from engine.tooling.plan_types import Action, Plan


class TestPlanNpcDialogue(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.test_dir.name)
        self.prev_cwd = Path.cwd()
        os.chdir(self.root)

        # Setup basic structure
        (self.root / "scenes").mkdir()
        self.scene_path = self.root / "scenes/test_scene.json"
        self.scene_path.write_text(json.dumps({
            "entities": [
                {"name": "Guard", "x": 0, "y": 0, "tag": "npc"}
            ]
        }))

    def tearDown(self):
        os.chdir(self.prev_cwd)
        self.test_dir.cleanup()

    def test_lint_valid_dialogue(self):
        plan = Plan(wizard="test", version=1, inputs={}, actions=[
            Action(type="add_npc_dialogue", args={
                "scene_path": "scenes/test_scene.json",
                "npc_name": "Guard",
                "lines": ["Hello", "World"]
            }, description="Add dialogue")
        ])
        issues = lint_ai_plan(plan)
        self.assertEqual(len(issues), 0)

    def test_lint_invalid_dialogue_length(self):
        plan = Plan(wizard="test", version=1, inputs={}, actions=[
            Action(type="add_npc_dialogue", args={
                "scene_path": "scenes/test_scene.json",
                "npc_name": "Guard",
                "lines": ["A" * 121] # Too long
            }, description="Add dialogue")
        ])
        issues = lint_ai_plan(plan)
        self.assertTrue(any(i.code == "CONSTRAINT_VIOLATION" for i in issues))

    def test_lint_invalid_dialogue_count(self):
        plan = Plan(wizard="test", version=1, inputs={}, actions=[
            Action(type="add_npc_dialogue", args={
                "scene_path": "scenes/test_scene.json",
                "npc_name": "Guard",
                "lines": ["Line"] * 9 # Too many
            }, description="Add dialogue")
        ])
        issues = lint_ai_plan(plan)
        self.assertTrue(any(i.code == "CONSTRAINT_VIOLATION" for i in issues))

    def test_execute_add_dialogue(self):
        plan = Plan(wizard="test", version=1, inputs={}, actions=[
            Action(type="add_npc_dialogue", args={
                "scene_path": "scenes/test_scene.json",
                "npc_name": "Guard",
                "lines": ["Halt!", "Who goes there?"],
                "dialogue_id": "guard_intro"
            }, description="Add dialogue")
        ])

        executor = PlanExecutor(dry_run=False, safe_paths_only=False)
        executor.execute(plan)

        # Verify
        with self.scene_path.open("r") as f:
            data = json.load(f)
            guard = data["entities"][0]
            self.assertIn("Dialogue", guard["behaviours"])
            self.assertEqual(guard["dialogue"]["lines"], ["Halt!", "Who goes there?"])
            self.assertEqual(guard["dialogue"]["id"], "guard_intro")
            self.assertEqual(guard["dialogue"]["speaker"], "Guard")
