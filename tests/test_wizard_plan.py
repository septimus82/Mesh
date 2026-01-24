import json
from unittest.mock import mock_open, patch

import pytest

from engine.tooling import wizard_command
from engine.tooling.tool_result import ToolResult


def _read_json_from_mock_open(mock_file_open) -> dict:
    handle = mock_file_open()
    written = "".join(call.args[0] for call in handle.write.call_args_list)
    return json.loads(written)


def test_dry_run_prints_plan_and_does_not_run_pipeline(capsys):
    with patch("engine.tooling.wizard_command.run_pipeline_result") as mock_run_pipeline, patch("builtins.open", new_callable=mock_open):
        mock_run_pipeline.side_effect = AssertionError("pipeline should not run during dry-run")
        ret = wizard_command.main(["new-questline", "--name-prefix", "test", "--plan", "plan.json", "--dry-run"])
        assert ret == 0

    out = capsys.readouterr().out
    assert '"wizard": "new-questline"' in out
    assert "Next step:" in out


def test_plan_output_builtin():
    with patch("builtins.open", new_callable=mock_open) as mock_file_open:
        ret = wizard_command.main(["new-questline", "--name-prefix", "test", "--plan", "plan.json", "--dry-run"])
        assert ret == 0

    data = _read_json_from_mock_open(mock_file_open)
    assert data["wizard"] == "new-questline"
    assert len(data["actions"]) > 0


def test_apply_runs_pipeline():
    with patch("engine.tooling.wizard_command.run_pipeline_result", return_value=ToolResult.success()) as mock_run_pipeline, patch("builtins.open", new_callable=mock_open):
        ret = wizard_command.main(["new-questline", "--name-prefix", "test", "--plan", "plan.json", "--apply"])
        assert ret == 0

    assert mock_run_pipeline.called


def test_fast_profile_sets_compact_only():
    with patch("builtins.open", new_callable=mock_open) as mock_file_open:
        ret = wizard_command.main(["new-questline", "--name-prefix", "test", "--plan", "plan.json", "--profile", "fast", "--dry-run"])
        assert ret == 0

    data = _read_json_from_mock_open(mock_file_open)
    polish_actions = [a for a in data["actions"] if a["type"] == "polish_scene"]
    assert polish_actions
    assert all(a["args"]["compact_only"] is True for a in polish_actions)
