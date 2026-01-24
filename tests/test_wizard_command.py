import pytest
from unittest.mock import mock_open, patch

from engine.tooling import wizard_command
class TestWizardCommand:
    @patch("engine.tooling.wizard_command.run_pipeline_result")
    @patch("builtins.open", new_callable=mock_open)
    def test_new_questline_flow(self, mock_file_open, mock_run_pipeline, capsys):
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
        mock_file_open.assert_called_with("plan.json", "w", encoding="utf-8")

    def test_unknown_subcommand(self):
        with pytest.raises(SystemExit):
            wizard_command.main(["unknown"])
