import unittest
import tempfile
import os
import json
from pathlib import Path
from engine.tooling import migrate_command

class TestMigrateCommand(unittest.TestCase):
    def test_detect_type(self):
        self.assertEqual(migrate_command.detect_type(Path("foo.json"), {"scenes": {}, "links": []}), "world")
        self.assertEqual(migrate_command.detect_type(Path("foo.json"), {"entities": [], "layers": []}), "scene")
        self.assertEqual(migrate_command.detect_type(Path("quests.json"), {}), "quests")
        
    def test_migrate_file(self):
        # Create a dummy scene v1
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as tmp:
            json.dump({"entities": [], "layers": [], "schema_version": 1}, tmp)
            tmp_path = tmp.name
            
        try:
            # Run migrate (dry run)
            # We need to mock argparse
            import argparse
            args = argparse.Namespace(path=tmp_path, write=False)
            
            # Since we have no actual migrations for scene > 1, it should just pass
            ret = migrate_command.handle_migrate(args)
            self.assertEqual(ret, 0)
            
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

if __name__ == "__main__":
    unittest.main()
