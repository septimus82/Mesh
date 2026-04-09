import unittest
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
from engine.tooling import content_commands
from tests.utils.args_factory import make_audit_trend_args

class TestAuditTrend(unittest.TestCase):
    def setUp(self):
        temp_root = Path("artifacts/test_tmp")
        temp_root.mkdir(parents=True, exist_ok=True)
        self._temp_dir = tempfile.TemporaryDirectory(dir=temp_root)
        self.test_dir = Path(self._temp_dir.name)
        self._old_cwd = Path.cwd()
        os.chdir(self.test_dir)
        
    def tearDown(self):
        os.chdir(self._old_cwd)
        self._temp_dir.cleanup()

    @patch("engine.tooling.content_commands.read_lock")
    def test_audit_trend_command(self, mock_read_lock):
        # Create dummy lock files
        lock1 = self.test_dir / "lock1.json"
        lock2 = self.test_dir / "lock2.json"
        
        lock1.touch()
        import time
        time.sleep(0.1)
        lock2.touch()
        
        # Mock read_lock to return different stats
        def side_effect(path):
            # Compare names because paths might differ in absolute/relative
            if path.name == "lock1.json":
                return {"audit_snapshot": {"unused_assets_count": 10, "unused_by_category": {"texture": 5}}}
            elif path.name == "lock2.json":
                return {"audit_snapshot": {"unused_assets_count": 15, "unused_by_category": {"texture": 8}}}
            return {}
            
        mock_read_lock.side_effect = side_effect
        
        args = make_audit_trend_args(
            locks="*.json",
            json=True
        )
        
        # Capture stdout
        from io import StringIO
        import sys
        captured_output = StringIO()
        sys.stdout = captured_output
        
        try:
            content_commands.audit_trend_command(args)
        finally:
            sys.stdout = sys.__stdout__
            
        output = captured_output.getvalue()
        data = json.loads(output)
        
        self.assertEqual(len(data), 2)
        # Sort by timestamp, but they were created same time. 
        # The command sorts by mtime.
        # Let's assume order.
        
        # Check deltas
        # One should have delta 0 (first), other +5
        deltas = [d["delta_total"] for d in data]
        self.assertIn(0, deltas)
        self.assertIn(5, deltas)

if __name__ == '__main__':
    unittest.main()
