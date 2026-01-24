import unittest
from unittest.mock import MagicMock, patch
import argparse
from mesh_cli import _handle_encounter_report
from engine.encounter_report import EncounterReport

class TestEncounterReportCLI(unittest.TestCase):
    @patch("mesh_cli.legacy_impl.generate_encounter_report")
    @patch("os.path.exists", return_value=True)
    @patch("builtins.open", new_callable=MagicMock)
    @patch("json.load")
    def test_cli_handler(self, mock_json_load, mock_open, mock_exists, mock_generate):
        # Setup args
        args = argparse.Namespace(
            path=["world.json"],
            json=True,
            out=None,
            themes="forest,cave",
            difficulty="easy,hard",
            only_dungeons=True
        )
        
        # Mock world file read
        mock_json_load.return_value = {"scenes": [{"path": "s1.json"}, {"path": "s2.json"}]}
        
        # Mock report result
        mock_report = EncounterReport()
        mock_generate.return_value = mock_report
        
        ret = _handle_encounter_report(args)
        
        self.assertEqual(ret, 0)
        
        # Verify generate called with correct args
        mock_generate.assert_called_once()
        call_args = mock_generate.call_args[1]
        self.assertEqual(call_args["scene_paths"], ["s1.json", "s2.json"])
        self.assertEqual(call_args["difficulties"], ["easy", "hard"])
        self.assertEqual(call_args["theme_filter"], ["forest", "cave"])
        self.assertEqual(call_args["only_dungeons"], True)
