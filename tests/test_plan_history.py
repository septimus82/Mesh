import shutil
import tempfile
import unittest
from pathlib import Path

from engine.tooling import plan_history
from engine.tooling.plan_types import Plan


class TestPlanHistory(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        # Monkey patch HISTORY_DIR
        self.original_dir = plan_history.HISTORY_DIR
        plan_history.HISTORY_DIR = self.test_dir

    def tearDown(self):
        plan_history.HISTORY_DIR = self.original_dir
        shutil.rmtree(self.test_dir)

    def test_record_and_list(self):
        plan = Plan(wizard="test", version=1, inputs={}, actions=[])
        result = {"status": "ok"}

        plan_history.record_history(plan, result, profile="test")

        history = plan_history.list_history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["wizard"], "test")

        details = plan_history.get_history(history[0]["id"])
        self.assertEqual(details["profile"], "test")

if __name__ == "__main__":
    unittest.main()
