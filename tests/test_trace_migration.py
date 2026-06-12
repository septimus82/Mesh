import json
import os
import tempfile
import unittest

from engine.tooling.event_trace import read_event_jsonl


class TestTraceMigration(unittest.TestCase):
    def test_migrate_v0_to_v1(self):
        # Create a v0 trace file (no schema_version, no timestamp)
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl") as tmp:
            tmp.write(json.dumps({"name": "old_event", "payload": {}}) + "\n")
            tmp_path = tmp.name

        try:
            # Read back - should auto-migrate
            events = list(read_event_jsonl(tmp_path))
            self.assertEqual(len(events), 1)
            e = events[0]
            self.assertEqual(e["name"], "old_event")
            self.assertEqual(e["schema_version"], 1)
            self.assertIn("timestamp", e)
            self.assertEqual(e["timestamp"], 0.0)

        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

if __name__ == "__main__":
    unittest.main()
