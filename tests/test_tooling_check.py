import unittest
import shutil
import json
from pathlib import Path
from engine.tooling import check

class TestToolingCheck(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("tests/temp_check")
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)
        self.test_dir.mkdir()
        
    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_check_missing_world(self):
        # Should fail if world doesn't exist
        self.assertFalse(check.run_check(str(self.test_dir / "missing.json")))

    def test_check_valid_world(self):
        # Create a minimal valid world and scene
        world_path = self.test_dir / "world.json"
        scene_path = self.test_dir / "scene.json"
        
        scene_data = {
            "name": "Scene",
            "version": 1,
            "entities": [],
            "layers": []
        }
        with open(scene_path, "w") as f:
            json.dump(scene_data, f)
            
        world_data = {
            "scenes": {
                "main": {"path": str(scene_path)}
            },
            "links": []
        }
        with open(world_path, "w") as f:
            json.dump(world_data, f)
            
        # We need to mock subprocess.run to avoid running actual pytest in this unit test
        # or we can just accept that it runs pytest?
        # Running pytest inside pytest is messy.
        # I'll mock subprocess.run.
        
        import subprocess
        from unittest.mock import patch, MagicMock
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            
            # We also need to make sure UnifiedValidator works relative to test_dir?
            # UnifiedValidator uses Path(".") by default in check.py.
            # check.py instantiates UnifiedValidator(Path("."), ...)
            # So it looks for files relative to CWD.
            # We need to change CWD or patch UnifiedValidator.
            
            # Let's patch UnifiedValidator to use self.test_dir
            with patch("engine.tooling.check.UnifiedValidator") as MockValidator:
                instance = MockValidator.return_value
                instance.validate_world.return_value = True
                instance.print_report.return_value = 0
                
                self.assertTrue(check.run_check(str(world_path)))
                
                # Verify it called validate_world
                instance.validate_world.assert_called()

    def test_check_with_replay(self):
        # Verify replay logic is triggered
        world_path = self.test_dir / "world.json"
        # Create dummy world file so validation passes check
        with open(world_path, "w") as f:
            json.dump({}, f)
            
        import subprocess
        from unittest.mock import patch, MagicMock
        
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            
            with patch("engine.tooling.check.UnifiedValidator") as MockValidator:
                instance = MockValidator.return_value
                instance.validate_world.return_value = True
                instance.print_report.return_value = 0
                
                # Run with replay trace
                trace_path = "some_trace.jsonl"
                self.assertTrue(check.run_check(str(world_path), replay_trace=trace_path))
                
                # Verify subprocess called mesh trace
                # mock_run is called twice: once for trace, once for smoke tests
                # We need to find the call that contains "trace"
                found_trace_call = False
                for call in mock_run.call_args_list:
                    cmd = call[0][0]
                    if "trace" in cmd and "--replay" in cmd:
                        found_trace_call = True
                        self.assertIn("mesh_cli.py", cmd)
                        self.assertIn(trace_path, cmd)
                        break
                
                self.assertTrue(found_trace_call, "Did not find subprocess call for trace replay")

if __name__ == "__main__":
    unittest.main()
