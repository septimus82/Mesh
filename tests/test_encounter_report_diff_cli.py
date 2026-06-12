"""Tests for encounter report diff CLI."""

import argparse
import unittest
from unittest.mock import patch

from mesh_cli import _handle_encounter_diff


class TestEncounterReportDiffCLI(unittest.TestCase):
    @patch("mesh_cli.legacy_impl.load_report")
    @patch("mesh_cli.legacy_impl.diff_reports")
    @patch("mesh_cli.legacy_impl._process_diff_result")
    def test_handle_diff(self, mock_process, mock_diff, mock_load):
        args = argparse.Namespace()

        _handle_encounter_diff("old.json", "new.json", args)

        self.assertEqual(mock_load.call_count, 2)
        mock_diff.assert_called_once()
        mock_process.assert_called_once()

    @patch("mesh_cli.load_report")
    def test_handle_diff_error(self, mock_load):
        mock_load.side_effect = Exception("Load error")
        args = argparse.Namespace()

        ret = _handle_encounter_diff("old.json", "new.json", args)
        self.assertEqual(ret, 1)

if __name__ == "__main__":
    unittest.main()
