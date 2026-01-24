import unittest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from engine.tooling import polish

class TestPolishUpdateLockAudit(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("tests/temp_polish_audit")
        self.test_dir.mkdir(exist_ok=True)
        self.scene_path = self.test_dir / "test_scene.json"
        self.scene_path.write_text(json.dumps({"id": "test"}))
        
    def tearDown(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    @patch("engine.tooling.polish.polish_scene")
    @patch("engine.tooling.polish.read_lock")
    @patch("engine.tooling.polish.write_lock")
    @patch("engine.tooling.polish.audit_world")
    def test_polish_update_audit(self, mock_audit, mock_write, mock_read, mock_polish_scene):
        mock_polish_scene.return_value = True
        mock_read.return_value = {"audit_snapshot": {}}
        mock_audit.return_value = {"stats": {"unused_assets_count": 5}}
        
        # Mock content.lock.json existence
        with patch("pathlib.Path.exists") as mock_exists:
            def side_effect(self):
                if self.name == "content.lock.json":
                    return True
                return True
            # We can't easily patch Path.exists for specific instances without side_effect
            # But since we are mocking read_lock/write_lock, we just need the check to pass.
            # The code checks Path("content.lock.json").exists()
            
            # Let's just create the file
            with open("content.lock.json", "w") as f:
                f.write("{}")
                
            try:
                polish.main(str(self.scene_path), update_lock_audit=True)
                
                mock_read.assert_called()
                mock_audit.assert_called()
                mock_write.assert_called()
                
                # Verify write content
                args = mock_write.call_args[0]
                data = args[1]
                self.assertEqual(data["audit_snapshot"]["unused_assets_count"], 5)
                
            finally:
                if Path("content.lock.json").exists():
                    Path("content.lock.json").unlink()

if __name__ == '__main__':
    unittest.main()
