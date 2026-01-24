import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from engine.tooling.plan_summary import summarize_plan


class TestPlanSummary(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_summarize_missing_file(self) -> None:
        result = summarize_plan("non_existent.plan.json")
        self.assertIn("Error: Plan file not found", result)

    def test_summarize_invalid_json(self) -> None:
        plan_path = self.root / "invalid.plan.json"
        plan_path.write_text("{ invalid json }", encoding="utf-8")
        result = summarize_plan(str(plan_path))
        self.assertIn("Error: Invalid JSON", result)

    def test_summarize_valid_plan(self) -> None:
        plan_data = {
            "wizard": "test",
            "version": 1,
            "inputs": {},
            "actions": [
                {
                    "type": "add_npc_dialogue",
                    "args": {
                        "scene_path": "scenes/hub.json",
                        "npc_name": "Greeter",
                        "dialogue_id": "intro",
                        "lines": ["Hello", "World"]
                    },
                    "description": "Add intro dialogue"
                },
                {
                    "type": "add_npc",
                    "args": {
                        "scene_path": "scenes/hub.json",
                        "role": "guard",
                        "name": "Guard1",
                        "x": 100,
                        "y": 100
                    },
                    "description": "Add a guard"
                },
                {
                    "type": "create_scene",
                    "args": {
                        "path": "scenes/dungeon.json",
                        "template": "dungeon"
                    },
                    "description": "Create dungeon"
                }
            ]
        }
        plan_path = self.root / "test.plan.json"
        plan_path.write_text(json.dumps(plan_data), encoding="utf-8")

        result = summarize_plan(str(plan_path))

        # Check header
        self.assertIn(f"Plan: {plan_path}", result)

        # Check Dialogue section
        self.assertIn("NPC Dialogue:", result)
        self.assertIn("scene: hub", result)
        self.assertIn("npc: Greeter", result)
        self.assertIn("dialogue_id: intro", result)
        self.assertIn("lines: 2", result)

        # Check Other Actions section
        self.assertIn("Other actions:", result)
        self.assertIn("add_npc: Add a guard", result)
        self.assertIn("(Add Guard1 to hub)", result)
        self.assertIn("create_scene: Create dungeon", result)
        self.assertIn("(Create scenes/dungeon.json from dungeon)", result)

if __name__ == "__main__":
    unittest.main()
