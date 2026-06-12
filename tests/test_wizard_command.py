from unittest.mock import ANY, patch

import pytest

from engine.tooling import wizard_command


class TestWizardCommand:
    @patch("engine.tooling.wizard_command.run_pipeline_result")
    @patch("engine.tooling.wizard_command.json_io.write_json_atomic")
    def test_new_questline_flow(self, mock_write_json, mock_run_pipeline, capsys):
        mock_run_pipeline.side_effect = AssertionError("wizard should not run pipeline unless --run/--apply is set")

        argv = [
            "new-questline",
            "--name-prefix",
            "TestQuest",
            "--scene",
            "scenes/test.json",
            "--plan",
            "plan.json",
            "--world",
            "worlds/main_world.json",
        ]
        ret = wizard_command.main(argv)
        assert ret == 0

        out = capsys.readouterr().out
        assert "Next step:" in out
        mock_write_json.assert_called_with("plan.json", ANY)

    def test_unknown_subcommand(self):
        with pytest.raises(SystemExit):
            wizard_command.main(["unknown"])
