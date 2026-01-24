import json
import os
import shutil
import unittest
from pathlib import Path
from engine.tooling import scaffold

class TestScaffold(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("tests/temp_scaffold")
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.test_dir.mkdir()

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_create_scene_templates(self):
        templates = ["empty", "topdown", "dialogue-playground", "overworld", "interior", "dungeon"]
        for tmpl in templates:
            path = self.test_dir / f"scene_{tmpl}.json"
            self.assertTrue(scaffold.create_scene(str(path), template_name=tmpl))
            self.assertTrue(path.exists())
            
            with open(path, "r") as f:
                data = json.load(f)
                self.assertEqual(data["version"], 1)
                # Check if entities are populated for non-empty templates
                if tmpl != "empty":
                    self.assertTrue(len(data["entities"]) > 0)

    def test_create_quest(self):
        quest_file = self.test_dir / "quests.json"
        
        # Create first quest
        self.assertTrue(scaffold.create_quest("My First Quest", str(quest_file)))
        self.assertTrue(quest_file.exists())
        
        with open(quest_file, "r") as f:
            data = json.load(f)
            self.assertEqual(len(data), 1)
            self.assertEqual(data[0]["id"], "my_first_quest")
            self.assertEqual(data[0]["title"], "My First Quest")

        # Create second quest
        self.assertTrue(scaffold.create_quest("Another Quest", str(quest_file)))
        
        with open(quest_file, "r") as f:
            data = json.load(f)
            self.assertEqual(len(data), 2)
            self.assertEqual(data[1]["id"], "another_quest")

        # Test duplicate
        self.assertFalse(scaffold.create_quest("My First Quest", str(quest_file)))

if __name__ == "__main__":
    unittest.main()
