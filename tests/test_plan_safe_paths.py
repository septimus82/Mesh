import shutil
import tempfile
import unittest
from pathlib import Path

from engine.tooling.plan_executor import PlanExecutor
from engine.tooling.plan_types import Plan


class TestPlanSafePaths(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.executor = PlanExecutor(dry_run=True, safe_paths_only=True)
        self.executor.current_plan = Plan(wizard="test", version=1, inputs={}, actions=[])

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_unsafe_path(self):
        # Path outside allowed areas
        unsafe_path = self.test_dir / "unsafe.txt"

        with self.assertRaises(Exception) as cm:
            self.executor._check_safety(unsafe_path)
        self.assertIn("Safety Violation", str(cm.exception))

    def test_safe_pack_path(self):
        # Mock pack input
        self.executor.current_plan.inputs["pack"] = "my_pack"

        # Path inside pack
        safe_path = Path.cwd() / "packs/my_pack/file.json"

        # Should not raise
        self.executor._check_safety(safe_path)

    def test_safe_scenes_path_no_pack(self):
        # No pack specified, scenes/ allowed
        safe_path = Path.cwd() / "scenes/level.json"
        self.executor._check_safety(safe_path)

if __name__ == "__main__":
    unittest.main()
