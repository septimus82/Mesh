import tempfile
import unittest
from pathlib import Path

from engine.test_reports.junit_writer import write_junit_report


class TestPlanTestJUnit(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.test_dir.name)

    def tearDown(self):
        self.test_dir.cleanup()

    def test_write_junit_report(self):
        report = {
            "passed": False,
            "tests": [
                {"name": "Test1", "type": "scene", "passed": True},
                {"name": "Test2", "type": "npc", "passed": False, "error": "NPC missing"}
            ],
            "coverage": {"actions_total": 10, "actions_covered": 5}
        }

        output_path = self.root / "report.xml"
        write_junit_report(report, str(output_path))

        self.assertTrue(output_path.exists())
        content = output_path.read_text(encoding="utf-8")

        self.assertIn('<testsuite name="MeshPlanTests"', content)
        self.assertIn('tests="2"', content)
        self.assertIn('failures="1"', content)
        self.assertIn('<testcase name="Test1"', content)
        self.assertIn('<testcase name="Test2"', content)
        self.assertIn('<failure message="NPC missing"', content)
