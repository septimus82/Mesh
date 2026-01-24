import unittest
import json
from unittest.mock import patch
from engine.tooling import doctor_command
from engine.tooling.tool_result import ToolResult
from tests.utils.args_factory import make_doctor_args

class TestDoctorCommand(unittest.TestCase):
    @patch("engine.tooling.doctor_command.DoctorRunner")
    def test_doctor_output(self, mock_runner_cls):
        mock_runner = mock_runner_cls.return_value
        report = {
            "version": 1,
            "target": "worlds/main_world.json",
            "summary": {"errors": 0, "warnings": 0, "checks": 2},
            "runs": [],
            "errors": [],
            "warnings": [],
            "suggested_next_commands": [],
        }
        mock_runner.run_result.return_value = ToolResult.from_doctor_report_dict(report)
        mock_runner.format_report.return_value = json.dumps(report)

        args = make_doctor_args(json=True, world="worlds/main_world.json")

        from io import StringIO
        import sys

        captured_output = StringIO()
        sys.stdout = captured_output
        try:
            ret = doctor_command.doctor_command(args)
        finally:
            sys.stdout = sys.__stdout__

        self.assertEqual(ret, 0)
        data = json.loads(captured_output.getvalue())
        self.assertEqual(data["version"], 1)
        self.assertIn("target", data)
        self.assertIn("summary", data)
        self.assertIn("runs", data)
        self.assertIn("errors", data)
        self.assertIn("warnings", data)
        self.assertIn("suggested_next_commands", data)

if __name__ == '__main__':
    unittest.main()
