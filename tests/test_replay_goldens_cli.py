import argparse
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.tooling import replay_goldens_command


class TestReplayGoldens(unittest.TestCase):
    def setUp(self):
        self.golden_dir = Path("traces/golden")
        self.golden_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        # Clean up created goldens
        for f in self.golden_dir.glob("test_trace*"):
            f.unlink()

    @patch("engine.tooling.trace_command.HeadlessGame")
    @patch("engine.tooling.trace_command.read_event_jsonl")
    @patch("engine.tooling.trace_command.verify_assertions")
    def test_replay_success(self, mock_verify, mock_read, mock_game):
        # Create dummy trace
        trace_path = self.golden_dir / "test_trace.jsonl"
        trace_path.write_text("")

        mock_read.return_value = []
        mock_verify.return_value = True

        args = argparse.Namespace(
            world="worlds/main.json",
            strict=False
        )

        ret = replay_goldens_command.handle_replay_goldens(args)
        self.assertEqual(ret, 0)

    @patch("engine.tooling.trace_command.HeadlessGame")
    @patch("engine.tooling.trace_command.read_event_jsonl")
    @patch("engine.tooling.trace_command.verify_assertions")
    def test_replay_fail_assertion(self, mock_verify, mock_read, mock_game):
        # Create dummy trace and assertion
        trace_path = self.golden_dir / "test_trace.jsonl"
        trace_path.write_text("")
        (self.golden_dir / "test_trace.assertions.json").write_text("{}")

        mock_read.return_value = []
        mock_verify.return_value = False

        args = argparse.Namespace(
            world="worlds/main.json",
            strict=False
        )

        ret = replay_goldens_command.handle_replay_goldens(args)
        self.assertEqual(ret, 1)
