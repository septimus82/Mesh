import json
import shutil
import unittest
from pathlib import Path
from engine.tooling import graph

class TestGraph(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("tests/temp_graph")
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.test_dir.mkdir()
        
        self.world_file = self.test_dir / "world.json"
        self.world_data = {
            "scenes": {
                "start": {"path": "scenes/start.json"},
                "end": {"path": "scenes/end.json"}
            },
            "links": [
                {"from": "start", "to": "end"}
            ]
        }
        with open(self.world_file, "w") as f:
            json.dump(self.world_data, f)

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_generate_dot_graph(self):
        dot = graph.generate_dot_graph(str(self.world_file))
        self.assertIn("digraph World {", dot)
        self.assertIn('"start" [label="start\\n(scenes/start.json)"];', dot)
        self.assertIn('"end" [label="end\\n(scenes/end.json)"];', dot)
        self.assertIn('"start" -> "end";', dot)

    def test_export_graph(self):
        output_file = self.test_dir / "graph.dot"
        self.assertTrue(graph.export_graph(str(self.world_file), str(output_file)))
        self.assertTrue(output_file.exists())
        
        with open(output_file, "r") as f:
            content = f.read()
            self.assertIn("digraph World {", content)

if __name__ == "__main__":
    unittest.main()
